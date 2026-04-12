<template src="./EditorView.html"></template>
<style scoped src="./EditorView.css"></style>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue';
import type { Ref } from 'vue';
// Some internal paths don't expose types to TS in this workspace; ignore resolution here
import { useEditorStore } from '@/stores/editor';
// Note: `CanvasEngine` is exported from `src/core/canvas-engine.ts`
import { CanvasEngine } from '@/core/canvas-engine';
import axios from 'axios';

// Local types
interface CropBox { x: number; y: number; w: number; h: number }
interface ImageMeta {
  id?: string;
  filename?: string;
  rotation?: number;
  deskew_angle?: number;
  brightness?: number;
  contrast?: number;
  bbox?: CropBox[];
  order?: number;
  __original?: any;
  _dirty?: boolean;
}

const emit = defineEmits(['back']);
const editorStore = useEditorStore();

// Per-image preview session tracking (prevents state leakage)
interface PreviewSession {
  imageId: string;
  imageIndex: number;
  transformReady: boolean;
  hasRequestedPreview: boolean;
  cropBoxCount: number;
}
let currentPreviewSession: PreviewSession | null = null;

// Pending bbox load intent (decoupled from session lifecycle)
let pendingBBoxImageId: string | null = null;
let pendingBBoxData: CropBox[] | null = null;

// State
const images: Ref<ImageMeta[]> = ref([] as ImageMeta[]);
const selectedIndex = ref<number>(0);
const mainCanvas = ref<HTMLCanvasElement | null>(null);
const canvasWrapper = ref<HTMLElement | null>(null);
const previewCanvas = ref<HTMLCanvasElement | null>(null);
const previewSection = ref<HTMLElement | null>(null);
const previewImg = ref<HTMLImageElement | null>(null);
const toolsPanel = ref<HTMLElement | null>(null);
const isMainCanvasVisible = ref<boolean>(false);
let _canvasObserver: IntersectionObserver | null = null;
const zoom = ref<number>(1);
const isLoading = ref<boolean>(false);
const isDirty = ref<boolean>(false);
const previewUrl = ref<string | null>(null);
const isImageLoading = ref<boolean>(false);
const isPreviewLoading = ref<boolean>(false);
const isPreviewVisible = ref<boolean>(false);
let _previewObserver: IntersectionObserver | null = null;
let _pendingPreviewExport = false;
let _previewObjectUrl: string | null = null;
let _previewLoadTimeout: number | null = null;
let _previewBlobSize: number | null = null;
let _pendingPreviewTimer: number | null = null;
let sceneVersion = 0;

// STATE LATCH: minimal, deterministic preview orchestration
const previewIntent = ref(false); // we WANT a preview
const transformReadyLatch = ref(false); // engine reports READY
const previewExported = ref(false); // export happened for current session

function markSceneDirty() {
  sceneVersion++;
}

/**
 * Single gate function to decide whether to trigger preview
 * This is the ONLY place preview export should be initiated
 * CRITICAL: Preview generation is a DATA PIPELINE - not dependent on UI visibility
 */
function maybeTriggerPreview(session: PreviewSession | null) {
  // STATE LATCH: record intent unconditionally (order must not matter)
  if (!session) return;

  if (!previewIntent.value) {
    previewIntent.value = true;
    // Log only the state transition required for proof
    console.log('previewIntent → true', { imageId: session.imageId, sceneVersion, timestamp: Date.now() });
  }
  // Keep compatibility flag for older guards
  session.hasRequestedPreview = true;
}

function isImageNodeReadyForExport(): boolean {
  try {
    const img = (canvasEngine as any)?.currentImage;
    if (!img) return false;
    const hasImg = !!img.image();
    const ox = typeof img.offsetX === 'function' ? img.offsetX() : (img.offsetX || 0);
    const oy = typeof img.offsetY === 'function' ? img.offsetY() : (img.offsetY || 0);
    const w = typeof img.width === 'function' ? img.width() : (img.width || 0);
    const h = typeof img.height === 'function' ? img.height() : (img.height || 0);
      // Previously we required non-zero offsets which prevented images
      // with rotation==0 from being considered ready. That check caused
      // previews to be skipped for many valid images. Only require the
      // image node and positive dimensions here; offset values may be
      // legitimately zero for unrotated images.
      return hasImg && (w > 0 && h > 0);
  } catch (e) {
    return false;
  }
}

// Canvas Engine (typed as any because upstream module types are unavailable)
let canvasEngine: CanvasEngine | null = null;
let previewCanvasEngine: CanvasEngine | null = null;
// When true we suppress preview updates triggered from CanvasEngine events
// while we are loading/initializing an image and its crop boxes.
let suspendPreviewUpdates = false;

// Adjustments
const currentRotation = ref<number>(0);
const currentBrightness = ref<number>(0);
const currentContrast = ref<number>(0);

// PDF generation
const showGenerateModal = ref(false);
const showProgress = ref(false);
const progressPercent = ref(0);
const progressMessage = ref('');
const pdfConfig = ref({
  quality: 'medium',
  paper_size: 'a4_fit'
});
const pdfPages = ref<Array<{ url: string; index: number }>>([]);
const showPdfPreview = ref(true);
const isPdfPreviewLoading = ref(false);

// Image adjustment state
let isAdjusting = false;
let proxyCanvas: HTMLCanvasElement | null = null;
let originalImageData: ImageData | null = null;

// Preview modal state
const showPreviewModal = ref<boolean>(false);
const previewZoom = ref<number>(1);
const showGrid = ref<boolean>(true);
const previewDimensions = ref<{ width: number; height: number; aspectRatio: string } | null>(null);
const previewCanvasSize = ref<{ width: number; height: number }>({ width: 0, height: 0 });
let isPanning = false;
let panStart = { x: 0, y: 0 };

// Server crop modal state
const showServerCropModal = ref<boolean>(false);
const serverCropUrl = ref<string | null>(null);
const serverCropDimensions = ref<{ width: number; height: number; aspectRatio: string } | null>(null);
const serverCropDebugInfo = ref<any>(null);

// Computed
const currentImage = computed<ImageMeta | null>(() => images.value[selectedIndex.value] ?? null);
const projectId = computed<string | null>(() => (editorStore.currentScan ? String(editorStore.currentScan).replace('.pdf', '') : null));

/**
 * Load project metadata
 */
async function loadProject(): Promise<void> {
  if (!editorStore.currentScan) return;
  
  isLoading.value = true;
  try {
    const response = await axios.get(`/api/projects/${projectId.value}/metadata`);
    images.value = (response.data.images || []).map((img: any, idx: number) => ({
      id: img.id || `img_${idx}`,
      filename: img.filename || img.source_file,
      rotation: img.rotation || 0,
      deskew_angle: img.deskew_angle || 0,
      brightness: img.brightness || 1.0,
      contrast: img.contrast || 1.0,
      bbox: img.bbox ? (Array.isArray(img.bbox) ? img.bbox : [img.bbox]) : [],
      order: img.order !== undefined ? img.order : idx,
      _dirty: false
      } as ImageMeta)).sort((a, b) => (a.order || 0) - (b.order || 0)).map((m: ImageMeta, idx: number) => {
        // Attach an immutable snapshot of original metadata so reset can restore it
        const raw = response.data.images[idx] || {};
        ;(m as any).__original = {
          rotation: raw.rotation || 0,
          deskew_angle: raw.deskew_angle || 0,
          brightness: raw.brightness || 1.0,
          contrast: raw.contrast || 1.0,
          bbox: raw.bbox ? (Array.isArray(raw.bbox) ? raw.bbox : [raw.bbox]) : []
        };
        return m;
      });
    
    // Set loading to false to show the UI
    isLoading.value = false;
    
    if (images.value.length > 0) {
      await nextTick();
      // Set initial selected index but defer loading the image until the
      // canvas is visible (lazy load). loadImageToCanvas will initialize
      // the CanvasEngine only when the DOM node is ready and visible.
      selectedIndex.value = 0;
      // Ensure the first image gets initialized. We still prefer lazy
      // initialization via IntersectionObserver, but call the helper as a
      // fallback in case the observer doesn't fire (see onMounted changes).
      try {
        await ensureCanvasEngineAndLoadSelected();
      } catch (err) {
        console.error('loadProject: ensureCanvasEngineAndLoadSelected failed', err);
      }
      // Kick off background PDF preview generation (non-blocking)
      try {
        setTimeout(() => {
          generatePdfPreviewForProject().catch(err => console.warn('Background preview generation failed', err));
        }, 100);
      } catch (e) {}
    }
  } catch (error) {
    console.error('Failed to load project:', error);
    alert('Failed to load project');
  }
}

// Project-level dirty indicator (true if any image is dirty)
const projectDirty = computed(() => images.value.some(img => !!img._dirty));

// Clear all edits across all images by restoring from each image's __original snapshot
function clearAllEdits(): void {
  console.log('clearAllEdits: Reset All clicked')

  // Mutate images in-place (avoids replacing the array reference which
  // can sometimes interfere with reactivity in certain setups).
  images.value.forEach((img, idx) => {
    const original = (img as any).__original || {};
    img.rotation = original.rotation || 0;
    img.deskew_angle = original.deskew_angle || 0;
    img.brightness = original.brightness || 1.0;
    img.contrast = original.contrast || 1.0;
    img.bbox = original.bbox ? (Array.isArray(original.bbox) ? JSON.parse(JSON.stringify(original.bbox)) : [JSON.parse(JSON.stringify(original.bbox))]) : [];
    img._dirty = false;
  });

  // Clear any preview and mark project as clean
  previewUrl.value = null;
  _previewBlobSize = null;
  isDirty.value = false;

  // Reload the current image to apply restored values on the canvas
  if (selectedIndex.value >= 0 && selectedIndex.value < images.value.length) {
    loadImageToCanvas(selectedIndex.value).catch(err => {
      console.error('clearAllEdits: failed to reload image after reset', err);
    });
  }
  // Ensure preview pipeline knows state changed
  try {
    markSceneDirty();
    schedulePreviewUpdate(sceneVersion);
    retryPendingPreviewIfReady();
    (canvasEngine as any)?._emit?.('modified', { source: 'programmatic' });
    try { lastExportToken = sceneVersion; updatePreview(sceneVersion); } catch (e) {}
  } catch (e) {}
}

/**
 * Load image to canvas
 */
async function loadImageToCanvas(index: number): Promise<void> {
  markSceneDirty();
  const image: ImageMeta | undefined = images.value[index];
  if (!image || !mainCanvas.value) {
    console.log('loadImageToCanvas: no image or canvas', image, mainCanvas.value);
    return;
  }
  const myIndex = index;
  
  try {
  isImageLoading.value = true;

  markSceneDirty();

  // Initialize CanvasEngine if needed
  if (!canvasEngine) {
    canvasEngine = new CanvasEngine(mainCanvas.value);

    // Listen to canvas events; use coalesced schedulePreviewUpdate
    canvasEngine.on('modified', (data: any) => {
      // Event-driven: CanvasEngine indicates whether the modification
      // was caused by a user action or programmatic lifecycle work.
      // Default to treating unknown emissions as user edits for
      // backward-compatibility.
      const source = data && data.source ? data.source : 'user';
      if (source === 'user') {
        // Ensure we record a scene change so coalesced preview scheduling
        // treats subsequent edits as new tokens. Without this, user
        // interactions (drag/resize) wouldn't bump `sceneVersion` and
        // `schedulePreviewUpdate` would ignore repeated tokens.
        markSceneDirty();
        markDirty();
      }
      if (!suspendPreviewUpdates && currentPreviewSession?.transformReady) {
        schedulePreviewUpdate(sceneVersion);
      }
      // Also retry any pending requests (e.g., if cropbox was just added)
      retryPendingPreviewIfReady();
    });

    canvasEngine.on('objectAdded', () => {
      markSceneDirty();
      if (currentPreviewSession) {
        currentPreviewSession.cropBoxCount = Math.min(1, (currentPreviewSession.cropBoxCount || 0) + 1);
      }
    });

    canvasEngine.on('objectDeleted', () => {
      markSceneDirty();
      if (currentPreviewSession) {
        currentPreviewSession.cropBoxCount = Math.max(0, (currentPreviewSession.cropBoxCount || 0) - 1);
      }
    });

    canvasEngine.on('imageLoaded', () => {
      // Image finished loading into CanvasEngine; mark stable
      markSceneDirty();
    });

    // CRITICAL: Listen for explicit transformReady event
    canvasEngine.on('transformReady', () => {
      console.log('🔧 ENGINE TRANSFORM_READY EVENT FIRED', {
        hasSession: !!currentPreviewSession,
        sessionId: currentPreviewSession?.imageId,
        hasPendingBBox: !!pendingBBoxImageId,
        pendingBBoxImageId,
        timestamp: Date.now()
      });
      
      if (currentPreviewSession) {
        currentPreviewSession.transformReady = true;
        // STATE LATCH: mark transform ready
        if (!transformReadyLatch.value) {
          transformReadyLatch.value = true;
          console.log('transformReady → true', { imageId: currentPreviewSession.imageId, timestamp: Date.now() });
        }
        console.log('✅ Set session.transformReady = true', currentPreviewSession.imageId);
        
        // Apply pending bbox if it matches current image (state replay)
        if (pendingBBoxImageId && pendingBBoxData && canvasEngine) {
          // CRITICAL GUARD: Verify pending bbox belongs to current image
          if (pendingBBoxImageId === currentPreviewSession.imageId) {
            try {
              canvasEngine.loadCropBoxes(pendingBBoxData);
              currentPreviewSession.cropBoxCount = Math.min(1, pendingBBoxData.length);
              markSceneDirty();
              console.log('✅ BBOX APPLIED AFTER TRANSFORM_READY (state replay)', { 
                imageId: pendingBBoxImageId, 
                bboxCount: pendingBBoxData.length,
                guardPassed: true
              });
              pendingBBoxImageId = null;
              pendingBBoxData = null;
            } catch (err) {
              console.error('❌ Failed to apply pending bbox', err);
            }
          } else {
            console.warn('⚠️ BBOX REPLAY BLOCKED: pendingBBoxImageId mismatch (race condition prevented)', {
              pendingBBoxImageId,
              currentSessionId: currentPreviewSession.imageId,
              guardPassed: false
            });
          }
        } else {
          console.log('📦 No pending bbox to apply');
        }
        
        // Use latch-driven gate: maybeTriggerPreview records intent; the combined
        // watcher will observe both latches and schedule export exactly once.
        console.log('🔍 Calling maybeTriggerPreview after transformReady...');
        maybeTriggerPreview(currentPreviewSession);

        // Retry pending preview checks too (preserve existing resilience)
        retryPendingPreviewIfReady();
      } else {
        console.warn('⚠️ transformReady fired but no current session!');
      }
    });

    canvasEngine.on('zoomChanged', (data: any) => {
      zoom.value = data.zoom;
    });
  }
  
  // Load image
  // IMPORTANT: Load 'original' or 'large' size WITHOUT any pre-applied rotations
  // because bbox coordinates are relative to the UNROTATED original image
  const imageUrl = getImageUrl(image.filename ?? '', 'large');
  
  // Get original image dimensions from metadata bbox if available
  // bbox is in original image coordinates, so we can infer the image was processed at full size
  // We need to load the 'original' size to know the true dimensions
  const originalUrl = getImageUrl(image.filename ?? '', 'original');
  const originalSize = await getImageSize(originalUrl);
  
  // Suppress preview exports while we configure the loaded image
  // Suppress preview updates while we configure the loaded image
  suspendPreviewUpdates = true;
  await canvasEngine.loadImage(imageUrl, originalSize.width);

  // Clear any CSS preview artifacts that might have been left on the wrapper
  if (canvasWrapper.value) {
    canvasWrapper.value.style.filter = '';
    canvasWrapper.value.style.transform = '';
    canvasWrapper.value.style.willChange = '';
  }

  // Initialize prev-applied values so we don't accidentally reapply stale transforms
  _prevAppliedRotation = currentRotation.value;
  _prevAppliedBrightness = currentBrightness.value;
  _prevAppliedContrast = currentContrast.value;
  
  // Load saved adjustments - display rotation = rotation + deskew_angle
  // Note: Negate rotation because metadata uses clockwise, should uses counter-clockwise
  const totalRotation = -((image.rotation || 0) + (image.deskew_angle || 0));
  currentRotation.value = totalRotation;
  currentBrightness.value = ((image.brightness || 1.0) - 1.0) * 100;  // Convert to -100..100
  currentContrast.value = ((image.contrast || 1.0) - 1.0) * 100;      // Convert to -100..100
  
  // NOTE: Do NOT load crop boxes yet. We must apply transforms first so
  // Konva image node has proper offsets/x/y/rotation. Loading bbox before
  // transforms results in stale or incorrect mapping. Bbox will be loaded
  // after transforms are applied below when TRANSFORM_READY is observed.
  
  // Apply rotation to canvas if needed - AFTER loading bbox
  // This will rotate both image and bbox together
  if (Math.abs(totalRotation) > 0.01) {
    applyRotation(totalRotation);
  }
  
  // Apply brightness/contrast if needed
  if (Math.abs(currentBrightness.value) > 0.1 || Math.abs(currentContrast.value) > 0.1) {
    applyBrightnessContrast();
  }

  // Create a new preview session for this image
  // CRITICAL: Rehydrate state from engine (may already be ready)
  const imageId = image.id ?? `img_${index}`;
  const engineReady = canvasEngine?.isTransformReady() ?? false;
  currentPreviewSession = {
    imageId: imageId,
    imageIndex: index,
    transformReady: engineReady,
    hasRequestedPreview: false,
    cropBoxCount: 0
  };
  // Reset state latch for this new session
  previewIntent.value = false;
  transformReadyLatch.value = engineReady;
  previewExported.value = false;
  console.log('📸 PREVIEW SESSION CREATED (data pipeline)', { 
    imageId,
    imageIndex: index,
    filename: image.filename,
    transformReady: engineReady,
    visibilityIrrelevant: true,
    timestamp: Date.now()
  });
  
  // If engine is already ready, trigger preview immediately
  if (engineReady) {
    console.log('loadImageToCanvas: engine already ready, triggering preview via gate');
    // Record preview intent if appropriate (keeps semantics compatible)
    maybeTriggerPreview(currentPreviewSession);
  }

  // Store bbox load intent (will be applied when transformReady event fires)
  // CRITICAL: Decouple bbox loading from session creation - bbox is per-IMAGE, not per-session
  if (image.bbox && image.bbox.length > 0) {
    pendingBBoxImageId = imageId;
    pendingBBoxData = JSON.parse(JSON.stringify(image.bbox));
    console.log('📦 BBOX INTENT STORED', { 
      imageId, 
      bboxCount: image.bbox.length,
      engineReady,
      willApplyImmediately: engineReady && !!canvasEngine
    });
    
    // If engine is already ready, apply bbox immediately
    if (engineReady && canvasEngine) {
      try {
        // GUARD: Verify we're still on the same image (prevent race condition)
        if (pendingBBoxImageId === imageId && currentPreviewSession?.imageId === imageId) {
          await nextTick();
          canvasEngine.loadCropBoxes(pendingBBoxData);
          if (currentPreviewSession) {
            currentPreviewSession.cropBoxCount = Math.min(1, pendingBBoxData.length);
          }
          markSceneDirty();
          console.log('✅ BBOX APPLIED IMMEDIATELY (engine already ready)', {
            imageId,
            bboxCount: pendingBBoxData.length
          });
          pendingBBoxImageId = null;
          pendingBBoxData = null;
        } else {
          console.warn('⚠️ BBOX APPLICATION SKIPPED: image changed during load', {
            pendingId: pendingBBoxImageId,
            targetId: imageId,
            currentSessionId: currentPreviewSession?.imageId
          });
        }
      } catch (err) {
        console.error('❌ Failed to apply bbox immediately', err);
      }
    }
  } else {
    // No bbox for this image - clear any pending intent
    console.log('📦 No bbox for image, clearing pending intent', { imageId });
    pendingBBoxImageId = null;
    pendingBBoxData = null;
  }
  
  // Preview will be triggered by transformReady event, no need for manual scheduling here
  } catch (error) {
    console.error('Failed to load image to canvas:', error);
  } finally {
    isImageLoading.value = false;
    suspendPreviewUpdates = false;
  }
}

/**
 * Select image
 */
async function selectImage(index: number): Promise<void> {
  // DO NOT preserve crop boxes across images - this causes state leakage
  // Each image must start with a clean slate
  
  // Destroy current preview session (no state bleeds across images)
  console.log('🗑️ DESTROYING PREVIEW SESSION + PENDING BBOX', {
    oldSessionId: currentPreviewSession?.imageId,
    oldPendingBBoxId: pendingBBoxImageId,
    newIndex: index,
    timestamp: Date.now()
  });
  currentPreviewSession = null;
  
  // Clear pending bbox intent (prevents cross-image leakage)
  pendingBBoxImageId = null;
  pendingBBoxData = null;

  // Reset latch state to avoid leaking intent across images
  previewIntent.value = false;
  transformReadyLatch.value = false;
  previewExported.value = false;

  // Reset preview lifecycle for the newly selected image
  try {
    // Clear any pending preview object URL
    if (_previewObjectUrl) {
      try { URL.revokeObjectURL(_previewObjectUrl); } catch (e) {}
      _previewObjectUrl = null;
    }
    previewUrl.value = null;
    _previewBlobSize = null;
    _pendingPreviewExport = false;
    if (_pendingPreviewTimer) {
      clearTimeout(_pendingPreviewTimer);
      _pendingPreviewTimer = null;
    }
    // Clear canvas crop boxes immediately so the new image starts fresh.
    try { canvasEngine?.clear(); } catch (e) {}
    // Bump sceneVersion to indicate a fresh lifecycle
    markSceneDirty();
  } catch (e) {
    // ignore errors during reset
  }

  selectedIndex.value = index;
  await loadImageToCanvas(index);
}

/**
 * Crop box management
 */
function addCropBox(): void {
  if (!canvasEngine) return;
  // Guard: if a crop already exists, do not add another
  try {
    const info = (canvasEngine as any).getCropBoxesInfoForOriginal?.() || [];
    if (Array.isArray(info) && info.length > 0) {
      console.warn('addCropBox: crop already exists, not adding another')
      return;
    }
  } catch (e) {}

  canvasEngine.addCropBox();
  markSceneDirty();
  markDirty();
}

function clearCrops() {
  if (!canvasEngine) return;
  canvasEngine.clear();
  markSceneDirty();
  markDirty();
  try {
    schedulePreviewUpdate(sceneVersion);
    retryPendingPreviewIfReady();
    (canvasEngine as any)?._emit?.('modified', { source: 'programmatic' });
    // Force immediate export and ensure token isn't considered stale
    try { lastExportToken = sceneVersion; updatePreview(sceneVersion); } catch (e) {}
  } catch (e) {}
}

function hasCrop(): boolean {
  try {
    if (!canvasEngine) return false;
    // Prefer querying engine info; fallback to DOM nodes
    const info = (canvasEngine as any).getCropBoxesInfoForOriginal?.();
    if (Array.isArray(info)) return info.length > 0;
    const nodes = (canvasEngine as any).cropLayer?.find?.('.cropBox') || [];
    return nodes.length > 0;
  } catch (e) {
    return false;
  }
}

async function cropFromMetadata(): Promise<void> {
  if (!currentImage.value || !projectId.value) return;

  try {
    const boxes = canvasEngine?.getCropBoxesForOriginal?.();
    // null means transform not ready, [] means no crops (both are valid)
    if (boxes === null) {
      console.warn('cropFromMetadata: transform not ready, aborting');
      alert('Cannot crop yet — image transform not ready');
      return;
    }

    currentImage.value.bbox = Array.isArray(boxes) ? boxes : [];

    let response;
    try {
      response = await axios.post(`/api/crop-from-metadata`, {
        project_id: projectId.value,
        image_index: selectedIndex.value,
        bbox: currentImage.value.bbox,
        rotation: currentRotation.value,
        brightness: currentBrightness.value / 100 + 1,
        contrast: currentContrast.value / 100 + 1
      });
    } catch (err: any) {
      console.error('cropFromMetadata: network/API error', err?.response ?? err);
      // Surface server body if present for easier debugging
      if (err?.response?.data) console.error('cropFromMetadata: response body', err.response.data);
      throw err;
    }

    console.log('cropFromMetadata: server response', response && response.data ? response.data : response);

    // Show in server crop modal
    if (response && response.data && response.data.cropped_url) {
      serverCropUrl.value = response.data.cropped_url;
      serverCropDimensions.value = {
        width: response.data.width,
        height: response.data.height,
        aspectRatio: calculateAspectRatio(response.data.width, response.data.height)
      };
      serverCropDebugInfo.value = response.data.debug_info;
      showServerCropModal.value = true;
    } else {
      console.warn('cropFromMetadata: no cropped_url in response', response?.data);
      alert('No cropped image returned');
    }

  } catch (error) {
    console.error('Failed to crop from metadata:', error);
    // If server returned an error body, show it to the user for debugging
    try {
      const body = error?.response?.data ?? null;
      if (body) {
        alert('Failed to crop from metadata: ' + (body.error || JSON.stringify(body)));
        return;
      }
    } catch (e) {}
    alert('Failed to crop from metadata');
  }
}

async function updatePreview(scheduledVersionOrToken?: number): Promise<void> {
  console.log('🎨 updatePreview STARTED', { 
    scheduledVersionOrToken, 
    sceneVersion,
    session: currentPreviewSession,
    lastExportToken,
    timestamp: Date.now() 
  });
  const exportStartTs = Date.now();
  
  if (!canvasEngine) return;
  
  // Check preview session validity (event-driven lifecycle)
  if (!currentPreviewSession) {
    console.debug('updatePreview: no active preview session — aborting');
    return;
  }
  
  if (!currentPreviewSession.transformReady) {
    console.debug('updatePreview: transform not ready in session — aborting');
    return;
  }
  
  // If the engine is still loading the image, defer the preview export
  if (isImageLoading.value) {
    console.debug('updatePreview: image still loading — aborting');
    return;
  }
  // If scene changed since scheduling, abort. Accept either a token or a sceneVersion snapshot.
  if (typeof scheduledVersionOrToken === 'number') {
    // If this number is an old token, abort (idempotency)
    if (scheduledVersionOrToken < lastExportToken && scheduledVersionOrToken !== sceneVersion) {
      console.debug('updatePreview: aborting because token is stale', { scheduledVersionOrToken, lastExportToken, sceneVersion });
      return;
    }
    if (scheduledVersionOrToken !== sceneVersion && scheduledVersionOrToken > lastExportToken) {
      // It's likely a sceneVersion snapshot that doesn't match current scene
      console.debug('updatePreview: aborting because sceneVersion changed', { scheduledVersionOrToken, sceneVersion });
      return;
    }
  }
  // Indicate loading so the UI can show a spinner while export runs
  isPreviewLoading.value = true;
  // Give Vue and the browser a chance to paint the loading spinner
  await nextTick();
  await new Promise(requestAnimationFrame);

  // Capture the selected index and session so we can ignore stale exports
  const exportIndex = selectedIndex.value;
  const exportSession = currentPreviewSession;

  // Export preview data from canvas engine lazily. The engine now
  // prefers returning a Blob to avoid large base64 strings. We create an
  // object URL for the blob and set it as the preview src.
  // Request a downscaled preview to keep UI responsive (smaller blob)
  const croppedData: { blob?: Blob; data?: string; width: number; height: number } | null = await canvasEngine.exportCropBoxFromOriginal({ format: 'png', quality: 0.8, previewMaxWidth: 800 });

  // Validate session hasn't changed during async export
  if (exportSession !== currentPreviewSession) {
    console.debug('updatePreview: session changed during export — discarding result');
    isPreviewLoading.value = false;
    return;
  }

  if (croppedData && (croppedData.blob || croppedData.data)) {
    console.debug('preview: export finished — preparing preview URL')
    // Only apply the exported data if the selection hasn't changed while
    // the export was running.
    if (exportIndex === selectedIndex.value) {
      try {
        // Revoke previous object URL if present
        if (_previewObjectUrl) {
          URL.revokeObjectURL(_previewObjectUrl);
          _previewObjectUrl = null;
        }

        if (croppedData.blob) {
          _previewObjectUrl = URL.createObjectURL(croppedData.blob);
          console.log('🖼️ PREVIEW BLOB CREATED + URL ASSIGNED', {
            blobSize: croppedData.blob.size,
            blobType: croppedData.blob.type,
            url: _previewObjectUrl,
            timestamp: Date.now()
          });
          previewUrl.value = _previewObjectUrl;
          _previewBlobSize = croppedData.blob.size || null;
        } else if (croppedData.data) {
          // Fallback path: when engine returned a data URL
          const res = await fetch(croppedData.data);
          const blob = await res.blob();
          _previewObjectUrl = URL.createObjectURL(blob);
          previewUrl.value = _previewObjectUrl;
          _previewBlobSize = blob.size || null;
        }
      } catch (err) {
        console.warn('Failed to set preview blob URL, falling back to direct data', err);
        previewUrl.value = (croppedData as any).data ?? null;
      }
      const pxW = Math.round(croppedData.width);
      const pxH = Math.round(croppedData.height);
      previewDimensions.value = {
        width: pxW,
        height: pxH,
        aspectRatio: calculateAspectRatio(pxW, pxH)
      };

      // Wait for the preview <img> to emit load (or error) so spinner/blur
      // can be visible while the browser decodes the image. Use a timeout
      // so we don't block indefinitely if the event doesn't fire.
      try {
        await new Promise<void>((resolve, reject) => {
          const imgEl = (previewImg as any)?.value as HTMLImageElement | null;
          if (!imgEl) return resolve();

          const onLoad = () => {
            console.log('🖼️ PREVIEW <img> LOADED', {
              src: imgEl?.src?.substring(0, 50) + '...',
              timestamp: Date.now()
            });
            if (_previewLoadTimeout) { clearTimeout(_previewLoadTimeout); _previewLoadTimeout = null; }
            imgEl.removeEventListener('load', onLoad);
            imgEl.removeEventListener('error', onError);
            resolve();
          };

          const onError = () => {
            if (_previewLoadTimeout) { clearTimeout(_previewLoadTimeout); _previewLoadTimeout = null; }
            imgEl.removeEventListener('load', onLoad);
            imgEl.removeEventListener('error', onError);
            reject(new Error('preview image load error'));
          };

          imgEl.addEventListener('load', onLoad);
          imgEl.addEventListener('error', onError);

          _previewLoadTimeout = window.setTimeout(() => {
            imgEl.removeEventListener('load', onLoad);
            imgEl.removeEventListener('error', onError);
            _previewLoadTimeout = null;
            resolve();
          }, 2000);
        });
      } catch (err) {
        // ignore errors from image load — still clear loading below
      }
    } else {
      console.debug('updatePreview: export ignored due to selection/session change');
    }
  } else {
    // Export returned null - either transform not ready or no crop boxes
    // This is a valid state: log for debugging but don't treat as error
    console.info('updatePreview: export returned null (transform not ready or no crop boxes)');
    isPreviewLoading.value = false;
    return;
  }
  isPreviewLoading.value = false;
  const exportEndTs = Date.now();
  // If we didn't get a blob size (e.g., previewUrl is a data: string), try to estimate
  let reportedSize: string | number = _previewBlobSize ?? 'unknown';
  if (!_previewBlobSize && previewUrl.value && typeof previewUrl.value === 'string' && previewUrl.value.startsWith('data:')) {
    // approximate: base64 length * 3 / 4
    const base64 = previewUrl.value.split(',')[1] || '';
    reportedSize = Math.round((base64.length * 3) / 4);
  }
  console.info(`preview: export complete — duration=${exportEndTs - exportStartTs}ms, blobSize=${reportedSize} bytes, url=${previewUrl.value}`)
}

/**
 * Calculate aspect ratio as simplified fraction
 */
function calculateAspectRatio(width: number, height: number): string {
  const gcd = (a: number, b: number): number => (b === 0 ? a : gcd(b, a % b));
  const divisor = gcd(width, height) || 1;
  const w = Math.round(width / divisor);
  const h = Math.round(height / divisor);
  
  // Common aspect ratios
  if (Math.abs(width/height - 4/3) < 0.02) return '4:3';
  if (Math.abs(width/height - 16/9) < 0.02) return '16:9';
  if (Math.abs(width/height - 1) < 0.02) return '1:1';
  if (Math.abs(width/height - 3/2) < 0.02) return '3:2';
  if (Math.abs(width/height - Math.sqrt(2)) < 0.02) return 'A4';
  
  return `${w}:${h}`;
}

function onPreviewImgLoad(): void {
  // Intentionally empty — the promise in updatePreview listens for load.
}

function onPreviewImgError(): void {
  // Ensure loading indicator is cleared on image error
  isPreviewLoading.value = false;
}

/**
 * Preview modal functions
 */
async function openPreviewModal() {
  if (!canvasEngine) return;
  
  showPreviewModal.value = true;
  
  // Wait for DOM to render
  await nextTick();
  
  // Initialize preview canvas engine
  await initPreviewCanvas();
}

function closePreviewModal() {
  showPreviewModal.value = false;
  
  // Cleanup preview canvas engine
  if (previewCanvasEngine) {
    previewCanvasEngine.destroy();
    previewCanvasEngine = null;
  }
}

function closeServerCropModal() {
  showServerCropModal.value = false;
  serverCropUrl.value = null;
  serverCropDimensions.value = null;
  serverCropDebugInfo.value = null;
}

/**
 * Export cropped region from ORIGINAL image with transformations applied
 * This replicates what will be in the final PDF
 * Uses canvas-engine's method to ensure consistency across UI and export
 */
async function exportCropFromOriginal() {
  if (!canvasEngine || !currentImage.value) return null;
  
  try {
    // Use canvas-engine's exportCropBoxFromOriginal method (options only)
    const croppedDataUrl = await canvasEngine.exportCropBoxFromOriginal({
      format: 'png',
      quality: 1
    });
    
    return croppedDataUrl;
    
  } catch (error) {
    console.error('Failed to export crop from original:', error);
    return null;
  }
}

// ----- Client-side PDF preview generation (lightweight, background) -----
// Preview settings (lightweight defaults)
const PREVIEW_PDF_DPI = 150; // preview DPI (lower than final 300 for speed)
const A4_POINTS = { width: 595, height: 842 }; // ReportLab A4 in points
const PREVIEW_MARGIN_POINTS = 10;

function ptsToPx(points: number, dpi = PREVIEW_PDF_DPI) {
  return Math.round((points * dpi) / 72.0);
}

function determineDocumentSpanClient(imgW: number, imgH: number, pageW: number, pageH: number, margin: number, dpi: number = 300) {
  const halfW = Math.floor(pageW / 2);
  const halfH = Math.floor(pageH / 2);
  const imgWpt = Math.floor((imgW * 72.0) / dpi);
  const imgHpt = Math.floor((imgH * 72.0) / dpi);

  const canFitInQuadrant = (qw: number, qh: number) => imgWpt <= Math.max(0, qw - 2 * margin) && imgHpt <= Math.max(0, qh - 2 * margin);

  if (canFitInQuadrant(halfW, halfH)) return 'single';

  const fullWAvail = Math.max(0, pageW - 2 * margin);
  const halfHAvail = Math.max(0, halfH - 2 * margin);
  if (imgWpt <= fullWAvail && imgHpt <= halfHAvail) return 'half_horizontal';

  const halfWAvail = Math.max(0, halfW - 2 * margin);
  const fullHAvail = Math.max(0, pageH - 2 * margin);
  if (imgWpt <= halfWAvail && imgHpt <= fullHAvail) return 'half_vertical';

  return 'full';
}

function computeDocumentPositionClient(bboxX: number, bboxY: number, bboxW: number, bboxH: number, scanW: number, scanH: number, imgW: number, imgH: number, pageW: number, pageH: number, margin: number, span: string, dpi: number = 300) {
  const imgWpt = Math.floor((imgW * 72.0) / dpi);
  const imgHpt = Math.floor((imgH * 72.0) / dpi);

  const cxNorm = (bboxX + bboxW / 2.0) / scanW;
  const cyNorm = (bboxY + bboxH / 2.0) / scanH;

  const halfW = Math.floor(pageW / 2);
  const halfH = Math.floor(pageH / 2);

  if (span === 'single') {
    let regionX = 0, regionY = 0, regionW = halfW, regionH = halfH;
    if (cxNorm < 0.5 && cyNorm < 0.5) { regionX = 0; regionY = halfH; }
    else if (cxNorm >= 0.5 && cyNorm < 0.5) { regionX = halfW; regionY = halfH; }
    else if (cxNorm < 0.5 && cyNorm >= 0.5) { regionX = 0; regionY = 0; }
    else { regionX = halfW; regionY = 0; }

    const drawX = regionX + margin;
    const drawY = regionY + regionH - margin - imgHpt;
    return { x: drawX, y: drawY, w: imgWpt, h: imgHpt };
  }

  if (span === 'half_horizontal') {
    let regionX = 0, regionY = cyNorm < 0.5 ? halfH : 0, regionW = pageW, regionH = halfH;
    let drawX = regionX + Math.floor((regionW - imgWpt) / 2);
    if (cxNorm < 0.33) drawX = regionX + margin;
    else if (cxNorm > 0.67) drawX = regionX + regionW - margin - imgWpt;
    const drawY = regionY + regionH - margin - imgHpt;
    return { x: drawX, y: drawY, w: imgWpt, h: imgHpt };
  }

  if (span === 'half_vertical') {
    let regionX = cxNorm < 0.5 ? 0 : halfW, regionW = halfW, regionH = pageH, regionY = 0;
    let drawY = regionY + Math.floor((regionH - imgHpt) / 2);
    if (cyNorm < 0.33) drawY = regionY + regionH - margin - imgHpt;
    else if (cyNorm > 0.67) drawY = regionY + margin;
    const drawX = regionX + margin;
    return { x: drawX, y: drawY, w: imgWpt, h: imgHpt };
  }

  // full page
  return { x: Math.floor((pageW - imgWpt) / 2), y: Math.floor((pageH - imgHpt) / 2), w: imgWpt, h: imgHpt };
}

async function generatePdfPreviewPagesForSelected(): Promise<void> {
  try {
    isPdfPreviewLoading.value = true;
    if (!canvasEngine || !currentImage.value) return;
    // Ensure engine ready and crop exists
    const crops = (canvasEngine as any).getCropBoxesInfoForOriginal?.() || [];
    if (!Array.isArray(crops) || crops.length === 0) return;

    // Export transformed crop (downscaled for preview)
    const exportRes = await (canvasEngine as any).exportCropBoxFromOriginal({ format: 'png', quality: 0.8, previewMaxWidth: 1200 });
    if (!exportRes || !exportRes.blob) return;

    // Get crop bbox and scan dims
    const cropInfo = crops[0];
    const bbox = cropInfo.bbox;
    const offsetX = cropInfo.offsetX || 0;
    const offsetY = cropInfo.offsetY || 0;
    const scanW = (canvasEngine as any).originalDimensions?.width || 0;
    const scanH = (canvasEngine as any).originalDimensions?.height || 0;
    const croppedWpx = exportRes.width || Math.round(bbox.w);
    const croppedHpx = exportRes.height || Math.round(bbox.h);

    // Determine layout span & position
    // Adjust DPI to account for downscaling in exportRes (to preserve physical size)
    const scaleRatio = (exportRes.width && bbox.w) ? (exportRes.width / Math.max(1, Math.round(bbox.w))) : 1.0;
    const metaDpi = currentImage.value && (currentImage.value as any).scan_dpi ? Number((currentImage.value as any).scan_dpi) : 300;
    const adjustedDpi = metaDpi * scaleRatio;
    const span = determineDocumentSpanClient(croppedWpx, croppedHpx, A4_POINTS.width, A4_POINTS.height, PREVIEW_MARGIN_POINTS, adjustedDpi);
    const pos = computeDocumentPositionClient(bbox.x + (offsetX || 0), bbox.y + (offsetY || 0), bbox.w, bbox.h, scanW, scanH, croppedWpx, croppedHpx, A4_POINTS.width, A4_POINTS.height, PREVIEW_MARGIN_POINTS, span, adjustedDpi);

    // Create page canvas sized to preview DPI
    const pagePxW = ptsToPx(A4_POINTS.width, PREVIEW_PDF_DPI);
    const pagePxH = ptsToPx(A4_POINTS.height, PREVIEW_PDF_DPI);
    const pageCanvas = document.createElement('canvas');
    pageCanvas.width = pagePxW;
    pageCanvas.height = pagePxH;
    const ctx = pageCanvas.getContext('2d');
    if (!ctx) return;

    // Fill white background
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, pagePxW, pagePxH);

    // Load exported blob into Image
    const imgUrl = URL.createObjectURL(exportRes.blob);
    const imgEl = await new Promise<HTMLImageElement>((resolve, reject) => {
      const i = new Image();
      i.onload = () => resolve(i);
      i.onerror = (e) => reject(new Error('Failed to load export image'));
      i.src = imgUrl;
    });

    // Compute draw coords in pixels
    const drawXpx = ptsToPx(pos.x, PREVIEW_PDF_DPI);
    const drawYpx = ptsToPx(pos.y, PREVIEW_PDF_DPI);
    const drawWpx = ptsToPx(pos.w, PREVIEW_PDF_DPI);
    const drawHpx = ptsToPx(pos.h, PREVIEW_PDF_DPI);

    // Draw the image into position (fit into computed box)
    ctx.drawImage(imgEl, 0, 0, imgEl.width, imgEl.height, drawXpx, drawYpx, drawWpx, drawHpx);

    // Convert to blob and add to pdfPages (replace previous preview)
    const blob = await new Promise<Blob | null>((resolve) => pageCanvas.toBlob((b) => resolve(b), 'image/jpeg', 0.85));
    if (blob) {
      const url = URL.createObjectURL(blob);
      // Replace pdfPages with this single preview for now
      pdfPages.value = [{ url, index: 0 }];
      // revoke helper image
      try { URL.revokeObjectURL(imgUrl); } catch (e) {}
    }

  } catch (e) {
    console.warn('generatePdfPreviewPagesForSelected failed', e);
  }
  finally {
    try { isPdfPreviewLoading.value = false; } catch (e) {}
  }
}

/**
 * Generate PDF preview for entire project using saved metadata bboxes.
 * - Iterates `images` (from metadata)
 * - Loads each image original URL
 * - Applies rotation/deskew via canvas transform
 * - Crops using saved bbox (bbox stored on image object from metadata)
 * - Lays out cropped images into A4 pages and produces preview images
 */
async function generatePdfPreviewForProject(): Promise<void> {
  try {
    if (!images.value || images.value.length === 0) return;
    isPdfPreviewLoading.value = true;

    // Prepare one page canvas for drawing
    const pagePxW = ptsToPx(A4_POINTS.width, PREVIEW_PDF_DPI);
    const pagePxH = ptsToPx(A4_POINTS.height, PREVIEW_PDF_DPI);

    const tempCanvas = document.createElement('canvas');
    const tempCtx = tempCanvas.getContext('2d');
    if (!tempCtx) return;

    // Debug flag: when true draw bbox overlay on transformed canvas and log geometry
    const ENABLE_DEBUG_LAYOUT_OVERLAY = true;

    // Collect cropped images (as Image elements + metadata)
    const croppedItems: Array<{ img: HTMLImageElement; bbox: any; scanW: number; scanH: number; width: number; height: number; scanDpi?: number }> = [];

    for (let idx = 0; idx < images.value.length; idx++) {
      const imgMeta = images.value[idx];
      const filename = imgMeta.filename;
      if (!filename) continue;

      // Use saved bbox on image object (metadata). It may be a single bbox or null.
      const bbox = imgMeta.bbox && imgMeta.bbox.length ? (Array.isArray(imgMeta.bbox) ? imgMeta.bbox[0] : imgMeta.bbox) : null;
      if (!bbox) {
        // skip images without bbox
        continue;
      }

      // Load original image (use API endpoint 'original')
      const url = getImageUrl(filename, 'original');
      if (!url) continue;

      try {
        const imgEl = await new Promise<HTMLImageElement>((resolve, reject) => {
          const i = new Image();
          i.crossOrigin = 'anonymous';
          i.onload = () => resolve(i);
          i.onerror = () => reject(new Error('failed to load')); 
          i.src = url;
        });

        const scanW = imgEl.width;
        const scanH = imgEl.height;

        // Determine scan DPI: prefer metadata value if present, else infer from pixel dimensions
        let scanDpi = 300;
        try {
          const mdDpi = (imgMeta as any).scan_dpi;
          if (mdDpi && Number(mdDpi) > 0) {
            scanDpi = Number(mdDpi);
          } else {
            // Infer from A4 dimensions (8.27" × 11.69") and snap to common DPI
            const scan_w_inch = 8.27;
            const scan_h_inch = 11.69;
            const dpi_w = scanW / scan_w_inch;
            const dpi_h = scanH / scan_h_inch;
            const inferred = (dpi_w + dpi_h) / 2.0;
            const common = [75, 100, 150, 200, 300, 600, 1200];
            scanDpi = common.reduce((best, v) => Math.abs(v - inferred) < Math.abs(best - inferred) ? v : best, common[0]);
          }
        } catch (e) {}

        // Apply full-image rotation/deskew first (expand canvas to fit rotated image)
        const rot = Number(imgMeta.rotation || 0) + Number(imgMeta.deskew_angle || 0);
        const rad = -(rot * Math.PI) / 180;
        const cos = Math.abs(Math.cos(rad));
        const sin = Math.abs(Math.sin(rad));
        const rotW = Math.round(imgEl.width * cos + imgEl.height * sin);
        const rotH = Math.round(imgEl.width * sin + imgEl.height * cos);

        const transformedCanvas = document.createElement('canvas');
        transformedCanvas.width = rotW;
        transformedCanvas.height = rotH;
        const tctx = transformedCanvas.getContext('2d');
        if (!tctx) continue;
        // white background
        tctx.fillStyle = '#ffffff';
        tctx.fillRect(0, 0, rotW, rotH);
        // draw rotated image centered
        tctx.translate(rotW / 2, rotH / 2);
        tctx.rotate(rad);
        tctx.drawImage(imgEl, -imgEl.width / 2, -imgEl.height / 2);

        // Now crop using bbox coordinates which are saved after transform
        // IMPORTANT: Do NOT recompute or adjust bbox x/y — use them exactly
        // as they are stored (they are coordinates on the already-rotated canvas).
        const bx = Math.max(0, (bbox.x || 0));
        const by = Math.max(0, (bbox.y || 0));
        const bw = Math.max(1, Math.round(bbox.w || 1));
        const bh = Math.max(1, Math.round(bbox.h || 1));

        if (ENABLE_DEBUG_LAYOUT_OVERLAY) {
          try {
            // Draw debug rectangle on transformed canvas to visualize where bbox maps
            const dbgCtx = transformedCanvas.getContext('2d');
            if (dbgCtx) {
              dbgCtx.save();
              dbgCtx.strokeStyle = 'red';
              dbgCtx.lineWidth = 3;
              dbgCtx.setLineDash([6, 4]);
              dbgCtx.strokeRect(bx, by, bw, bh);
              dbgCtx.restore();
            }
            console.log('DEBUG_LAYOUT: transformed canvas', { filename, rot, rotW, rotH, bbox: { bx, by, bw, bh }, scanW, scanH });
          } catch (e) {
            console.warn('DEBUG_LAYOUT failed', e);
          }
        }

        const cropCanvas = document.createElement('canvas');
        cropCanvas.width = bw;
        cropCanvas.height = bh;
        const cropCtx = cropCanvas.getContext('2d');
        if (!cropCtx) continue;

        // Apply brightness/contrast AFTER crop as requested
        const brightnessFactor = (imgMeta.brightness !== undefined) ? Number(imgMeta.brightness) : 1.0;
        const contrastFactor = (imgMeta.contrast !== undefined) ? Number(imgMeta.contrast) : 1.0;
        // Canvas filter expects percentages (100% = 1.0)
        const bPct = Math.round(brightnessFactor * 100);
        const cPct = Math.round(contrastFactor * 100);
        cropCtx.filter = `brightness(${bPct}%) contrast(${cPct}%)`;

        // draw from transformed canvas into crop canvas
        cropCtx.drawImage(transformedCanvas, bx, by, bw, bh, 0, 0, bw, bh);

        croppedItems.push({ img: cropCanvas as unknown as HTMLImageElement, bbox, scanW, scanH, width: cropCanvas.width, height: cropCanvas.height, scanDpi });

      } catch (e) {
        console.warn('Failed processing image for preview', filename, e);
        continue;
      }
    }

    // Layout documents onto pages using a client-side port of server's layout_documents_smart
    // Build doc_items in the same shape as server: [span, (ignored_pos), img, scan_dpi]
    const docItems: Array<[string, any, HTMLCanvasElement, number]> = [];
    for (const item of croppedItems) {
      // Use per-item scan DPI when determining span/physical size
      const span = determineDocumentSpanClient(item.width, item.height, A4_POINTS.width, A4_POINTS.height, PREVIEW_MARGIN_POINTS, item.scanDpi || 300);
      docItems.push([span, [0, 0], item.img as unknown as HTMLCanvasElement, item.scanDpi || 300]);
    }

    // Client port of layout_documents_smart from server
    function layoutDocumentsSmartClient(doc_items: Array<[string, any, HTMLCanvasElement, number]>, page_w: number, page_h: number, margin: number) {
      if (!doc_items || doc_items.length === 0) return [];
      const pages: Array<Array<[string, [number, number], HTMLCanvasElement, number]>> = [];
      let current_page: Array<[string, [number, number], HTMLCanvasElement, number]> = [];
      const quadrantsOccupied: Record<string, boolean> = { tl: false, tr: false, bl: false, br: false };

      const quadrantPositions: Record<string, [number, number]> = {
        tl: [margin, Math.floor(page_h / 2)],
        tr: [Math.floor(page_w / 2) + margin, Math.floor(page_h / 2)],
        bl: [margin, 0],
        br: [Math.floor(page_w / 2) + margin, 0]
      };

      function startNewPage() {
        if (current_page.length) pages.push(current_page);
        current_page = [];
        quadrantsOccupied.tl = quadrantsOccupied.tr = quadrantsOccupied.bl = quadrantsOccupied.br = false;
      }

      function checkAndPlace(required: string[], spanType: string, imgRef: HTMLCanvasElement, dpiRef: number, posFunc: () => [number, number]) {
        const allAvailable = required.every(q => !quadrantsOccupied[q]);
        if (!allAvailable) startNewPage();
        const [dx, dy] = posFunc();
        current_page.push([spanType, [dx, dy], imgRef, dpiRef]);
        required.forEach(q => { quadrantsOccupied[q] = true; });
      }

      for (let i = 0; i < doc_items.length; i++) {
        const [span, _pos, img, dpi] = doc_items[i];
        if (span === 'single') {
          if (!quadrantsOccupied.tl) checkAndPlace(['tl'], span, img, dpi, () => quadrantPositions.tl);
          else if (!quadrantsOccupied.tr) checkAndPlace(['tr'], span, img, dpi, () => quadrantPositions.tr);
          else if (!quadrantsOccupied.bl) checkAndPlace(['bl'], span, img, dpi, () => quadrantPositions.bl);
          else if (!quadrantsOccupied.br) checkAndPlace(['br'], span, img, dpi, () => quadrantPositions.br);
          else checkAndPlace(['tl'], span, img, dpi, () => quadrantPositions.tl);
        } else if (span === 'half_horizontal') {
          if (!quadrantsOccupied.tl && !quadrantsOccupied.tr) checkAndPlace(['tl', 'tr'], span, img, dpi, () => quadrantPositions.tl);
          else if (!quadrantsOccupied.bl && !quadrantsOccupied.br) checkAndPlace(['bl', 'br'], span, img, dpi, () => quadrantPositions.bl);
          else checkAndPlace(['tl', 'tr'], span, img, dpi, () => quadrantPositions.tl);
        } else if (span === 'half_vertical') {
          if (!quadrantsOccupied.tl && !quadrantsOccupied.bl) checkAndPlace(['tl', 'bl'], span, img, dpi, () => quadrantPositions.tl);
          else if (!quadrantsOccupied.tr && !quadrantsOccupied.br) checkAndPlace(['tr', 'br'], span, img, dpi, () => quadrantPositions.tr);
          else checkAndPlace(['tl', 'bl'], span, img, dpi, () => quadrantPositions.tl);
        } else { // full
          // full forces a fresh page
          startNewPage();
          pages.push([[span, [margin, margin], img, dpi]]);
          startNewPage();
        }
      }

      if (current_page.length) pages.push(current_page);
      return pages;
    }

    const packedPages = layoutDocumentsSmartClient(docItems, A4_POINTS.width, A4_POINTS.height, PREVIEW_MARGIN_POINTS);

    const pages: HTMLCanvasElement[] = [];
    for (const p of packedPages) {
      const pageCanvas = document.createElement('canvas');
      pageCanvas.width = pagePxW; pageCanvas.height = pagePxH;
      const pctx = pageCanvas.getContext('2d')!;
      pctx.fillStyle = '#ffffff'; pctx.fillRect(0,0,pagePxW,pagePxH);
      for (const [span, [draw_x_pt, draw_y_pt], imgRef, dpiRef] of p) {
        // imgRef is cropped canvas sized in pixels; convert physical pts to preview px
        const imgWpx = (imgRef.width || imgRef.clientWidth || 0);
        const imgHpx = (imgRef.height || imgRef.clientHeight || 0);
        // Determine actual span box w/h in points. For single/half/full, compute target w/h
        let target_w_pt = 0, target_h_pt = 0;
        if (span === 'single') { target_w_pt = A4_POINTS.width / 2 - 2 * PREVIEW_MARGIN_POINTS; target_h_pt = A4_POINTS.height / 2 - 2 * PREVIEW_MARGIN_POINTS; }
        else if (span === 'half_horizontal') { target_w_pt = A4_POINTS.width - 2 * PREVIEW_MARGIN_POINTS; target_h_pt = A4_POINTS.height / 2 - 2 * PREVIEW_MARGIN_POINTS; }
        else if (span === 'half_vertical') { target_w_pt = A4_POINTS.width / 2 - 2 * PREVIEW_MARGIN_POINTS; target_h_pt = A4_POINTS.height - 2 * PREVIEW_MARGIN_POINTS; }
        else { target_w_pt = A4_POINTS.width - 2 * PREVIEW_MARGIN_POINTS; target_h_pt = A4_POINTS.height - 2 * PREVIEW_MARGIN_POINTS; }

        // Fit image into target box preserving aspect ratio (no upscale)
        const imgWpt = Math.floor((imgWpx * 72.0) / dpiRef);
        const imgHpt = Math.floor((imgHpx * 72.0) / dpiRef);
        let finalWpt = imgWpt, finalHpt = imgHpt;
        if (imgWpt > target_w_pt || imgHpt > target_h_pt) {
          const scale = Math.min(target_w_pt / imgWpt, target_h_pt / imgHpt);
          finalWpt = Math.floor(imgWpt * scale);
          finalHpt = Math.floor(imgHpt * scale);
        }

        // Compute final draw position in points (center within allocated area)
        let final_x_pt = draw_x_pt;
        let final_y_pt = draw_y_pt;
        const Wpt = A4_POINTS.width;
        const Hpt = A4_POINTS.height;
        if (span === 'half_horizontal') {
          // center horizontally within full width
          final_x_pt = (Wpt - finalWpt) / 2.0;
          final_y_pt = draw_y_pt; // draw_y_pt already is top-of-half region
        } else if (span === 'half_vertical') {
          // center vertically within full height
          final_y_pt = (Hpt - finalHpt) / 2.0;
          final_x_pt = draw_x_pt; // draw_x_pt is left-of-half region
        } else if (span === 'single') {
          // quadrant: determine which column/row based on region origin
          const half_w = Math.floor(Wpt / 2);
          const half_h = Math.floor(Hpt / 2);
          // draw_x_pt is region_x (either 0+margin or half_w+margin)
          if (draw_x_pt < half_w) {
            final_x_pt = draw_x_pt + (half_w - 2 * PREVIEW_MARGIN_POINTS - finalWpt) / 2.0;
          } else {
            final_x_pt = draw_x_pt + (half_w - 2 * PREVIEW_MARGIN_POINTS - finalWpt) / 2.0;
          }
          if (draw_y_pt >= half_h) {
            final_y_pt = draw_y_pt + (half_h - 2 * PREVIEW_MARGIN_POINTS - finalHpt) / 2.0;
          } else {
            final_y_pt = draw_y_pt + (half_h - 2 * PREVIEW_MARGIN_POINTS - finalHpt) / 2.0;
          }
        } else {
          // full page: center on page
          final_x_pt = (Wpt - finalWpt) / 2.0;
          final_y_pt = (Hpt - finalHpt) / 2.0;
        }

        const drawXpx = ptsToPx(final_x_pt, PREVIEW_PDF_DPI);
        const drawYpx = ptsToPx(final_y_pt, PREVIEW_PDF_DPI);
        const drawWpx = ptsToPx(finalWpt, PREVIEW_PDF_DPI);
        const drawHpx = ptsToPx(finalHpt, PREVIEW_PDF_DPI);

        try {
          pctx.drawImage(imgRef as any, 0, 0, imgWpx, imgHpx, drawXpx, drawYpx, drawWpx, drawHpx);
        } catch (e) {
          console.warn('Failed draw packed item', e);
        }
      }
      pages.push(pageCanvas);
    }

    // Convert pages to blobs/urls
    const previews: Array<{ url: string; index: number }> = [];
    for (let i = 0; i < pages.length; i++) {
      const p = pages[i];
      const blob = await new Promise<Blob | null>((resolve) => p.toBlob((b) => resolve(b), 'image/jpeg', 0.8));
      if (blob) {
        previews.push({ url: URL.createObjectURL(blob), index: i });
      }
    }

    // Assign to pdfPages
    pdfPages.value = previews;

  } catch (e) {
    console.warn('generatePdfPreviewForProject failed', e);
  } finally {
    try { isPdfPreviewLoading.value = false; } catch (e) {}
  }
}

// UI handler to force refresh preview and open preview pane
async function openPdfPreviewPanel(): Promise<void> {
  try {
    // If preview is already loading, just open pane and return
    if (!pdfPages.value || pdfPages.value.length === 0) {
      await generatePdfPreviewPagesForSelected();
    }
    // Ensure preview section is visible in UI
    showPdfPreview.value = true;
  } catch (e) {
    console.error('openPdfPreviewPanel failed', e);
    alert('Failed to generate PDF preview');
  }
}

/**
 * Khởi tạo Full Preview Modal
 */
async function initPreviewCanvas(): Promise<void> {
  if (!previewCanvas.value || !canvasEngine) return;

  try {
    // Use canvas-engine's export function (no args -> default png)
    const cropped = await canvasEngine.exportCropBoxFromOriginal();

    if (!cropped || !cropped.data) return;

    if (!previewCanvasEngine) {
      previewCanvasEngine = new CanvasEngine(previewCanvas.value);
    }

    // Load exported data URL into the preview engine
    await previewCanvasEngine.loadImage(cropped.data, cropped.width);
    previewCanvasEngine.centerView();
  } catch (error) {
    console.error('Failed to init preview:', error);
  }
}

function toggleGrid() {
  showGrid.value = !showGrid.value;
}

function previewZoomIn() {
  if (previewCanvasEngine) {
    previewCanvasEngine.zoomIn();
  }
}

function previewZoomOut() {
  if (previewCanvasEngine) {
    previewCanvasEngine.zoomOut();
  }
}

function resetPreviewZoom() {
  if (previewCanvasEngine) {
    previewCanvasEngine.resetZoom();
  }
}

function centerPreviewView() {
  if (previewCanvasEngine) {
    previewCanvasEngine.centerView();
  }
}

/**
 * Apply rotation to canvas image
 */
function applyRotation(angle: number): void {
  if (!canvasEngine) return;
  canvasEngine.applyRotation(angle);
  markSceneDirty();
  // Update preview (coalesced) so crop preview reflects rotation
  schedulePreviewUpdate(sceneVersion);
  _prevAppliedRotation = angle;
}

/**
 * Apply brightness and contrast filters
 */
function applyBrightnessContrast(): void {
  if (!canvasEngine) return;
  canvasEngine.applyFilters({
    brightness: currentBrightness.value / 100,
    contrast: currentContrast.value / 100
  });
  markSceneDirty();
  // Update preview (coalesced) so crop preview reflects filters
  schedulePreviewUpdate(sceneVersion);
}
 
// Coalesce preview updates using requestAnimationFrame to avoid expensive
// exportCropBoxFromOriginal() running on every tiny input event.
let _previewUpdateScheduled = false;
// Coalesce preview updates using a token and edge-triggering to avoid
// duplicate exports when multiple events fire for the same logical state.
let lastExportToken = 0;
let _prevPreviewReady = false;
// Track pending preview request that was dropped due to preview not ready
// Will be retried when preview becomes ready (state-driven retry)
let pendingPreviewToken: number | null = null;

/**
 * Helper: Retry pending preview request if conditions are now met
 */
function retryPendingPreviewIfReady(): void {
  if (pendingPreviewToken === null) return;
  
  // Check if preview is now ready
  const canExportNow = (() => {
    try {
      if (!canvasEngine) return false;
      if (isImageLoading.value) return false;
      if (!isImageNodeReadyForExport()) return false;
      const crops = (canvasEngine as any).getCropBoxesInfoForOriginal?.() || [];
      if (!Array.isArray(crops) || crops.length === 0) return false;
      return true;
    } catch (e) {
      return false;
    }
  })();
  
  if (canExportNow) {
    console.log('🔄 RETRY TRIGGER: preview now ready, retrying pending request', {
      pendingPreviewToken,
      timestamp: Date.now()
    });
    const tokenToRetry = pendingPreviewToken;
    // Don't clear here - let schedulePreviewUpdate handle it
    schedulePreviewUpdate(tokenToRetry);
  }
}

function schedulePreviewUpdate(token?: number): void {
  const tk = typeof token === 'number' ? token : sceneVersion;
  console.log('📅 schedulePreviewUpdate CALLED', { 
    token, 
    tk, 
    lastExportToken,
    timestamp: Date.now() 
  });
  // Default token to current sceneVersion snapshot if none provided

  // If token is not newer than the last export token, ignore (idempotent)
  if (tk <= lastExportToken) {
    console.debug('schedulePreviewUpdate: ignoring token <= lastExportToken', { tk, lastExportToken });
    return;
  }

  // Edge-trigger: only schedule an export when we transition into a ready state
  const canExportNow = (() => {
    try {
      if (!canvasEngine) return false;
      if (isImageLoading.value) return false;
      if (!isImageNodeReadyForExport()) return false;
      const crops = (canvasEngine as any).getCropBoxesInfoForOriginal?.() || [];
      if (!Array.isArray(crops) || crops.length === 0) return false;
      return true;
    } catch (e) {
      return false;
    }
  })();

  if (!canExportNow) {
    // Not ready — store this request for retry when preview becomes ready
    _prevPreviewReady = false;
    pendingPreviewToken = tk;
    console.log('⏸️ schedulePreviewUpdate: preview not ready, STORING request for retry', { 
      tk, 
      pendingPreviewToken,
      timestamp: Date.now() 
    });
    return;
  }

  // If we already considered preview ready for a previous token, and
  // token isn't newer than lastExportToken, skip scheduling.
  // Otherwise claim the token and schedule the export.
  lastExportToken = tk;
  _prevPreviewReady = true;
  // Clear pending token since we're processing this request now
  if (pendingPreviewToken === tk) {
    console.log('✅ schedulePreviewUpdate: processing PENDING request', { tk });
    pendingPreviewToken = null;
  }

  if (_previewUpdateScheduled) return;
  _previewUpdateScheduled = true;

  const now = Date.now();
  const sinceLast = now - _lastPreviewTs;

  const runNow = sinceLast >= PREVIEW_THROTTLE_MS;

  const run = async () => {
    _previewUpdateScheduled = false;
    try {
      // Use the current authoritative export token to avoid running with
      // a stale token that was captured when the run was originally scheduled.
      await updatePreview(lastExportToken);
      _lastPreviewTs = Date.now();
    } catch (err) {
      console.error('Failed to update preview:', err);
    }
  };

  // Use rAF for smoother UI when running immediately, otherwise delay to respect throttle
  if (runNow) {
    requestAnimationFrame(run);
  } else {
    const delay = Math.max(0, PREVIEW_THROTTLE_MS - sinceLast);
    setTimeout(() => requestAnimationFrame(run), delay);
  }
}

// Adjustment observer: batches rotation/brightness/contrast changes and applies
// them once per animation frame for smooth UI and minimal expensive exports.
let _adjustmentScheduled = false;
// Remember last applied values to avoid reapplying unchanged transforms
let _prevAppliedRotation = NaN;
let _prevAppliedBrightness = NaN;
let _prevAppliedContrast = NaN;
let _lastPreviewTs = 0;
const PREVIEW_THROTTLE_MS = 10;

function notifyAdjustmentChange(): void {
  const rot = currentRotation.value;
  const bri = currentBrightness.value;
  const con = currentContrast.value;

  const rotationChanged = rot !== _prevAppliedRotation;
  const brightnessChanged = bri !== _prevAppliedBrightness;
  const contrastChanged = con !== _prevAppliedContrast;

  // If user is actively dragging, avoid doing expensive Konva operations.
  // Use CSS preview for instant feedback and DO NOT export previews until finish.
  if (isAdjusting) {
    return;
  }

  // Not adjusting — apply only changes to Konva to minimize work
  if (canvasEngine) {
    if (rotationChanged) {
      // applyRotation schedules a preview update
      canvasEngine.applyRotation(rot);
      _prevAppliedRotation = rot;
      schedulePreviewUpdate(sceneVersion);
    }

    if (brightnessChanged || contrastChanged) {
      canvasEngine.applyFilters({ brightness: bri / 100, contrast: con / 100 });
      _prevAppliedBrightness = bri;
      _prevAppliedContrast = con;
      // ensure preview reflects filters
      schedulePreviewUpdate(sceneVersion);
    }
  }
}

/**
 * Brightness/Contrast adjustment handlers
 */
function startBrightnessAdjust() {
  isAdjusting = true;
  enableCssPreview(true);
}

function onBrightnessInput() {
  if (isAdjusting) {
    applyCssFilter();
    // still schedule the coalesced export so preview updates at rAF rate
    notifyAdjustmentChange();
  }
}

function finishBrightnessAdjust() {
  isAdjusting = false;
  // Apply the final filters to Konva and mark dirty
  enableCssPreview(false);
  applyBrightnessContrast();
  // record applied
  _prevAppliedBrightness = currentBrightness.value;
  _prevAppliedContrast = currentContrast.value;
  markDirty();
}

function startContrastAdjust() {
  isAdjusting = true;
  enableCssPreview(true);
}

function onContrastInput() {
  if (isAdjusting) {
    applyCssFilter();
    notifyAdjustmentChange();
  }
}

function finishContrastAdjust() {
  isAdjusting = false;
  enableCssPreview(false);
  applyBrightnessContrast();
  _prevAppliedBrightness = currentBrightness.value;
  _prevAppliedContrast = currentContrast.value;
  markDirty();
}

/**
 * Handle rotation adjustment
 */
function startRotationAdjust() {
  isAdjusting = true;
}

function handleAdjustment(): void {
  if (isAdjusting) {
    // While dragging, apply rotation directly to Konva so crop boxes remain upright
    if (canvasEngine) {
      try {
        canvasEngine.applyRotation(currentRotation.value);
        _prevAppliedRotation = currentRotation.value;
      } catch (err) {
        // fallback: schedule a coalesced update
        notifyAdjustmentChange();
      }
    }
  } else {
    notifyAdjustmentChange();
  }
}

// Apply CSS transform/filters to the canvas wrapper for instant lightweight preview
function applyCssFilter(): void {
  if (!canvasWrapper.value) return;
  const brightness = currentBrightness.value;
  const contrast = currentContrast.value;
  // Map to CSS filter values: brightness(%) contrast(%). Convert -100..100 to 0..200%
  const cssBrightness = 100 + brightness; // -100 -> 0%, 0 -> 100%, +100 -> 200%
  const cssContrast = 100 + contrast;
  canvasWrapper.value.style.filter = `brightness(${cssBrightness}%) contrast(${cssContrast}%)`;
}

function applyCssRotation(): void {
  // CSS rotation intentionally disabled because it rotates the entire stage
  // (including bbox). Rotation should be applied via Konva so bbox stays upright.
}

function enableCssPreview(enabled: boolean): void {
  if (!canvasWrapper.value) return;
  if (!enabled) {
    // Remove css preview styles
    canvasWrapper.value.style.filter = '';
    canvasWrapper.value.style.transform = '';
    canvasWrapper.value.style.willChange = '';
  } else {
    applyCssFilter();
    applyCssRotation();
    // Hint to the compositor to promote to its own layer
    canvasWrapper.value.style.willChange = 'transform, filter';
  }
}

function finishRotationAdjust() {
  isAdjusting = false;
  // Apply final rotation and update preview
  applyRotation(currentRotation.value);
  _prevAppliedRotation = currentRotation.value;
  markDirty();
}

/**
 * Handle rotation change
 */
watch(currentRotation, () => {
  if (currentImage.value) {
    // Keep UI responsive when currentRotation is changed programmatically
    notifyAdjustmentChange();
  }
});

/**
 * STATE-DRIVEN RETRY: Watch for preview becoming ready and retry pending requests
 * This ensures preview requests are never lost due to async timing
 */
watch(
  () => {
    // Compute preview readiness (same logic as schedulePreviewUpdate)
    try {
      if (!canvasEngine) return false;
      if (isImageLoading.value) return false;
      if (!isImageNodeReadyForExport()) return false;
      const crops = (canvasEngine as any).getCropBoxesInfoForOriginal?.() || [];
      if (!Array.isArray(crops) || crops.length === 0) return false;
      return true;
    } catch (e) {
      return false;
    }
  },
  (previewReady, prevReady) => {
    // Only trigger on transition from not-ready → ready
    if (previewReady && !prevReady && pendingPreviewToken !== null) {
      console.log('🔄 PREVIEW READY TRANSITION: retrying pending request', {
        pendingPreviewToken,
        timestamp: Date.now()
      });
      const tokenToRetry = pendingPreviewToken;
      // Don't clear pendingPreviewToken here - let schedulePreviewUpdate clear it
      schedulePreviewUpdate(tokenToRetry);
    }
  }
);

// STATE LATCH WATCHER: combine previewIntent + transformReadyLatch
watch(
  [() => previewIntent.value, () => transformReadyLatch.value],
  ([intent, ready]) => {
    // Only act when both true and we haven't exported yet
    if (!intent) return;
    if (!ready) return;
    if (previewExported.value) return;

    // Mark exported and schedule a single export
    previewExported.value = true;
    console.log('previewExported → true', { imageId: currentPreviewSession?.imageId, sceneVersion, timestamp: Date.now() });
    // Use sceneVersion token to schedule export (idempotent)
    schedulePreviewUpdate(sceneVersion);
  }
);

/**
 * Reset adjustments
 */
function resetAdjustments() {
  // Restore original metadata for the current image if available
  const img = currentImage.value;
  if (!img) return;

  const original = (img as any).__original || {
    rotation: 0,
    deskew_angle: 0,
    brightness: 1.0,
    contrast: 1.0,
    bbox: []
  };

  // Restore UI values (convert brightness/contrast from 1.0 base to -100..100 slider)
  const totalRotation = -((original.rotation || 0) + (original.deskew_angle || 0));
  currentRotation.value = totalRotation;
  currentBrightness.value = ((original.brightness || 1.0) - 1.0) * 100;
  currentContrast.value = ((original.contrast || 1.0) - 1.0) * 100;

  // Restore bbox on canvas
  if (canvasEngine) {
    // Ensure any CSS preview is cleared before applying Konva transforms
    enableCssPreview(false);

    canvasEngine.clear();
    if (original.bbox && original.bbox.length > 0) {
      canvasEngine.loadCropBoxes(original.bbox.map((b: any) => ({ ...b })));
    }

    // Apply rotation and filters from original
    applyRotation(currentRotation.value);
    applyBrightnessContrast();

    // Force a redraw to ensure canvas reflects rotation immediately
    try {
      canvasEngine.imageLayer.batchDraw();
      canvasEngine.centerView();
    } catch (err) {
      // ignore if internals unavailable
    }
  }

  // Update prev-applied markers so we don't reapply unnecessarily
  _prevAppliedRotation = currentRotation.value;
  _prevAppliedBrightness = currentBrightness.value;
  _prevAppliedContrast = currentContrast.value;
  // Persist restored values into the image metadata so switching images keeps reset state
  if (currentImage.value) {
    currentImage.value.rotation = -(currentRotation.value);
    currentImage.value.deskew_angle = 0;
    currentImage.value.brightness = 1.0 + (currentBrightness.value / 100);
    currentImage.value.contrast = 1.0 + (currentContrast.value / 100);
    currentImage.value.bbox = original.bbox && original.bbox.length > 0 ? original.bbox.map((b: any) => ({ ...b })) : [];
  }

  // Not dirty immediately after reset (we're back to original) — clear only current image
  if (currentImage.value) currentImage.value._dirty = false;
  isDirty.value = images.value.some(img => !!img._dirty);

  // Ensure the preview pipeline notices the reset: bump scene version,
  // emit a programmatic 'modified' event from the canvas engine and
  // schedule a preview update. Also attempt an immediate export via
  // `updatePreview()` (no token) to avoid stale-token abort races.
  try {
    markSceneDirty();
    if (canvasEngine) canvasEngine._emit?.('modified', { source: 'programmatic' });
  } catch (e) {
    // ignore
  }

  try {
    schedulePreviewUpdate(sceneVersion);
    // Force immediate export and set token so updatePreview won't abort
    try { lastExportToken = sceneVersion; updatePreview(sceneVersion); } catch (e) {}
  } catch (e) {}
}

/**
 * Mark as dirty
 */
function markDirty(): void {
  isDirty.value = true;
  if (currentImage.value) currentImage.value._dirty = true;
  if (currentImage.value) {
    currentImage.value.rotation = -currentRotation.value;
    currentImage.value.deskew_angle = 0;
    currentImage.value.brightness = 1.0 + (currentBrightness.value / 100);
    currentImage.value.contrast = 1.0 + (currentContrast.value / 100);
  }
}

/**
 * Save metadata
 */
async function handleSave(): Promise<void> {
  try {
    // Save current crop boxes
    // Use getCropBoxesForOriginal() to get bbox in unrotated original image coordinates
    if (canvasEngine && currentImage.value) {
      const boxes = canvasEngine.getCropBoxesForOriginal();
      // null means transform not ready (unlikely at save time), [] means no crops
      currentImage.value.bbox = (boxes === null) ? [] : boxes;
    }
    
    // Only send minimal editable fields per-image to the server.
    // Server will merge these into authoritative metadata.
    const editableImages = images.value.map(img => ({
      id: img.id,
      filename: img.filename,
      rotation: img.rotation,
      deskew_angle: img.deskew_angle,
      brightness: img.brightness,
      contrast: img.contrast,
      bbox: img.bbox && img.bbox.length > 0 ? (img.bbox.length === 1 ? img.bbox[0] : img.bbox) : null
    }));

    const metadata = { images: editableImages };
    
    console.log('Sending metadata:', metadata);
    await axios.put(`/api/projects/${projectId.value}/metadata`, metadata);
    // Clear dirty flags per-image and project dirty indicator
    images.value.forEach(img => { img._dirty = false; });
    isDirty.value = false;
    console.log('✅ Saved');
  } catch (error) {
    console.error('Save failed:', error);
    alert('Failed to save changes');
  }
}

/**
 * Generate PDF with SSE
 */
async function handleGenerate() {
  // Save current state first
  await handleSave();
  
  showGenerateModal.value = false;
  showProgress.value = true;
  progressPercent.value = 0;
  pdfPages.value = [];
  
  const eventSource = new EventSource(
    `/api/projects/${projectId.value}/generate?` +
    new URLSearchParams(pdfConfig.value as any)
  );
  
  eventSource.onmessage = (event: MessageEvent) => {
    const data = JSON.parse(event.data as string) as any;
    
    if (data.error) {
      eventSource.close();
      showProgress.value = false;
      alert(`Error: ${data.error}`);
      return;
    }
    
    progressPercent.value = data.progress;
    progressMessage.value = data.message;
    
    // Collect page previews as they're processed
    if (data.page_preview) {
      pdfPages.value.push({
        url: data.page_preview,
        index: pdfPages.value.length
      });
    }
    
    if (data.progress === 100) {
      eventSource.close();
      setTimeout(() => {
        showProgress.value = false;
        // Load final PDF pages from generated images
        loadPdfPages();

        // Auto-download first generated file if server provided URLs
        try {
          if (data.files && Array.isArray(data.files) && data.files.length > 0) {
            const first = data.files.find(f => f.type === 'color') || data.files[0];
            if (first && first.url) {
              const a = document.createElement('a');
              a.href = first.url;
              a.download = '';
              document.body.appendChild(a);
              a.click();
              a.remove();
            }
          }
        } catch (e) {
          console.warn('Auto-download failed', e);
        }

        alert('PDF generated successfully!');
      }, 1000);
    }
  };
  
  eventSource.onerror = () => {
    eventSource.close();
    showProgress.value = false;
    alert('PDF generation failed');
  };
}

/**
 * Load PDF pages preview from generated output
 */
async function loadPdfPages(): Promise<void> {
  try {
    // Get output images from project
    const response = await axios.get(`/api/projects/${projectId.value}/output`);
    if (response.data.images) {
      pdfPages.value = response.data.images.map((filename: string, idx: number) => ({
        url: getImageUrl(filename, 'medium'),
        index: idx
      }));
    }
  } catch (error) {
    console.error('Failed to load PDF pages:', error);
  }
}

/**
 * Zoom controls
 */
function zoomIn(): void {
  if (canvasEngine) {
    canvasEngine.zoomIn();
  }
}

function zoomOut(): void {
  if (canvasEngine) {
    canvasEngine.zoomOut();
  }
}

function resetCropBoxes(): void {
  if (!canvasEngine) return;

  const img = currentImage.value;
  let boxesToLoad: any[] | null = null;

  if (img) {
    const original = (img as any).__original;
    if (original && original.bbox && original.bbox.length > 0) {
      boxesToLoad = original.bbox.map((b: any) => ({ ...b }));
      // persist restored bbox back into current metadata
      img.bbox = boxesToLoad;
    } else if (img.bbox && img.bbox.length > 0) {
      boxesToLoad = img.bbox.map((b: any) => ({ ...b }));
    }
  }

  canvasEngine.clear();
  markSceneDirty();
  if (boxesToLoad && boxesToLoad.length > 0) {
    // Only restore the first bbox to enforce single-crop behavior
    canvasEngine.loadCropBoxes([boxesToLoad[0]]);
    markSceneDirty();
  }

  // After reset to original, not dirty
  if (currentImage.value) currentImage.value._dirty = false;
  isDirty.value = images.value.some(img => !!img._dirty);

  // Ensure the preview pipeline is aware of this programmatic reset.
  // Mark scene dirty so tokens advance, then schedule a coalesced preview
  // update and retry any pending preview exports.
  try {
    markSceneDirty();
    schedulePreviewUpdate(sceneVersion);
    retryPendingPreviewIfReady();
  } catch (e) {
    // ignore if scheduling helpers unavailable
  }
  try {
    // Notify canvas listeners that a programmatic modification occurred
    // so any event-driven logic (including preview scheduling) executes.
    (canvasEngine as any)?._emit?.('modified', { source: 'programmatic' });
  } catch (e) {
    // ignore
  }
  // Use coalesced update to avoid immediate double exports
  schedulePreviewUpdate(sceneVersion);
}

function centerView(): void {
  if (canvasEngine) {
    canvasEngine.resetView();
  }
}

/**
 * Helper functions
 */
// Get image dimensions without loading full image
function getImageSize(url: string): Promise<{ width: number; height: number }> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      resolve({ width: img.width, height: img.height });
    };
    img.onerror = () => reject(new Error('Failed to load image'));
    img.src = url;
  });
}

// Image URL construction - use secure API endpoint with size parameter
function getImageUrl(filename: string | undefined, size = 'medium'): string {
  // Endpoint: /api/images/{filename}?project_id={project_id}&size={size}
  // - Generates thumbnails on-demand with disk caching
  // - Sizes: thumbnail (200px), medium (800px), large (1600px), original
  // - Original images stay in scan_inbox (not copied)
  const backendUrl = 'http://localhost:8099';
  
  if (!filename) return '';
  
  // Handle legacy 'path' field (convert to filename)
  const cleanFilename = filename.includes('/') || filename.includes('\\')
    ? filename.split(/[/\\]/).pop() || ''
    : filename;
  
  // Get project ID from computed value
  const pid = projectId.value;
  if (!pid) return '';

  return `/api/images/${cleanFilename}?project_id=${pid}&size=${size}`;
}

function getThumbnailUrl(filename: string | undefined): string {
  return getImageUrl(filename, 'thumbnail');
}

// Lifecycle
onMounted(() => {
  // Setup IntersectionObserver to lazily initialize canvas when visible
  try {
    _canvasObserver = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (entry.target === canvasWrapper.value) {
          if (entry.isIntersecting) {
            isMainCanvasVisible.value = true;
            ensureCanvasEngineAndLoadSelected().catch(err => console.error(err));
          } else {
            isMainCanvasVisible.value = false;
          }
        }
      }
    }, { threshold: 0.05 });

    // Observe after DOM refs settle to avoid missing the initial intersection
    nextTick(() => {
      try {
        if (canvasWrapper.value && _canvasObserver) {
          _canvasObserver.observe(canvasWrapper.value);
          // Perform an immediate check — some browsers don't fire observer
          // callbacks if the element is already visible at observe-time.
          const rect = canvasWrapper.value.getBoundingClientRect();
          const visible = rect.top < window.innerHeight && rect.bottom > 0 && rect.left < window.innerWidth && rect.right > 0;
          if (visible) {
            isMainCanvasVisible.value = true;
            ensureCanvasEngineAndLoadSelected().catch(err => console.error(err));
          }
        }
      } catch (e) {
        // ignore
      }
    });
  } catch (err) {
    // IntersectionObserver may not be available in all environments; fall
    // back to immediate load.
    console.warn('IntersectionObserver unavailable, falling back to eager load', err);
    isMainCanvasVisible.value = true;
  }

  // Setup IntersectionObserver for preview container to defer preview export
  try {
    // Use the tools panel as the intersection root so visibility is
    // calculated within that scrolling container.
    const observerOptions: IntersectionObserverInit = { threshold: 0.05 };
    if (toolsPanel && (toolsPanel as any).value) observerOptions.root = (toolsPanel as any).value;

    _previewObserver = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (entry.target === (previewSection as any)?.value) {
          if (entry.isIntersecting) {
            console.log('👁️ IntersectionObserver: PREVIEW PANE NOW VISIBLE (UI only)', {
              wasVisible: isPreviewVisible.value,
              previewUrl: !!previewUrl.value,
              timestamp: Date.now()
            });
            isPreviewVisible.value = true;
            // Visibility only affects UI rendering - preview export runs independently
          } else {
            console.log('👁️ IntersectionObserver: PREVIEW PANE NOW HIDDEN (UI only)', {
              wasVisible: isPreviewVisible.value
            });
            isPreviewVisible.value = false;
          }
        }
      }
    }, { threshold: 0.05 });

    // previewSection is a template ref; we'll observe it if present after a tick
    nextTick(() => {
      try {
        const el = (previewSection as any)?.value as HTMLElement | null;
        if (_previewObserver && el) {
          _previewObserver.observe(el);
          // Immediate visibility check in case observer won't fire for
          // already-visible elements at observe-time.
          try {
            const rect = el.getBoundingClientRect();
            const root = ((toolsPanel as any)?.value as HTMLElement) || document.documentElement;
            const rootRect = root === document.documentElement ? { top: 0, left: 0, bottom: window.innerHeight, right: window.innerWidth } : root.getBoundingClientRect();
            const intersects = !(rect.right < rootRect.left || rect.left > rootRect.right || rect.bottom < rootRect.top || rect.top > rootRect.bottom);
            console.log('👁️ Immediate visibility check (UI only):', {
              intersects,
              previewUrl: !!previewUrl.value
            });
            if (intersects) {
              isPreviewVisible.value = true;
              // Visibility is UI-only - doesn't affect preview generation
            }
          } catch (e) {
            // ignore
          }
        }
      } catch (e) {
        // ignore
      }
    });
  } catch (err) {
    console.warn('Preview IntersectionObserver unavailable, assuming visible (UI only)', err);
    isPreviewVisible.value = true;
    // Preview export runs independently regardless of observer availability
  }

  // Load project metadata (image list). Actual image-to-canvas loading is
  // deferred until the canvas becomes visible.
  loadProject();
});

onBeforeUnmount(() => {
  // Cleanup
  if (canvasEngine) {
    canvasEngine.destroy();
    canvasEngine = null;
  }
  if (_canvasObserver && canvasWrapper.value) {
    try { _canvasObserver.unobserve(canvasWrapper.value); } catch (e) {}
    try { _canvasObserver.disconnect(); } catch (e) {}
    _canvasObserver = null;
  }
  if (_previewObserver && (previewSection as any)?.value) {
    try { _previewObserver.unobserve((previewSection as any).value); } catch (e) {}
    try { _previewObserver.disconnect(); } catch (e) {}
    _previewObserver = null;
  }
  if (_pendingPreviewTimer) {
    try { clearTimeout(_pendingPreviewTimer); } catch (e) {}
    _pendingPreviewTimer = null;
  }
  // Revoke any preview object URL we created
  if (_previewObjectUrl) {
    try { URL.revokeObjectURL(_previewObjectUrl); } catch (e) {}
    _previewObjectUrl = null;
  }
  // nothing special on unmount
});

/**
 * Ensure CanvasEngine exists and the currently selected image is loaded.
 * This is safe to call multiple times; it will no-op if already initialized.
 */
async function ensureCanvasEngineAndLoadSelected(): Promise<void> {
  // If there are no images, nothing to do
  if (!images.value || images.value.length === 0) return;

  // If canvasEngine already exists and the selected image is already loaded,
  // simply return. We can't easily detect whether a particular index is
  // loaded in CanvasEngine, so we conservatively call loadImageToCanvas when
  // the engine was not yet created.
  if (canvasEngine) return;

  // Wait a tick so DOM refs settle (mainCanvas must be present)
  await nextTick();

  // If mainCanvas isn't mounted yet, bail out
  if (!mainCanvas.value) return;

  // Initialize and load the selected image
  try {
    await loadImageToCanvas(selectedIndex.value ?? 0);
  } catch (err) {
    console.error('ensureCanvasEngineAndLoadSelected failed', err);
  }
}
</script>