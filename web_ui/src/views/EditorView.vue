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
  __original?: any;
  _dirty?: boolean;
}

const emit = defineEmits(['back']);
const editorStore = useEditorStore();

// State
const images: Ref<ImageMeta[]> = ref([] as ImageMeta[]);
const selectedIndex = ref<number>(0);
const mainCanvas = ref<HTMLCanvasElement | null>(null);
const canvasWrapper = ref<HTMLElement | null>(null);
const previewCanvas = ref<HTMLCanvasElement | null>(null);
const zoom = ref<number>(1);
const isLoading = ref<boolean>(false);
const isDirty = ref<boolean>(false);
const previewUrl = ref<string | null>(null);

// Canvas Engine (typed as any because upstream module types are unavailable)
let canvasEngine: CanvasEngine | null = null;
let previewCanvasEngine: CanvasEngine | null = null;

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
      _dirty: false
      } as ImageMeta)).map((m: ImageMeta, idx: number) => {
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
    
    console.log('loadProject: loaded images', images.value.length);
    
    // Set loading to false to show the UI
    isLoading.value = false;
    
    if (images.value.length > 0) {
      await nextTick();
      console.log('loadProject: calling selectImage(0)');
      await selectImage(0);
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
  isDirty.value = false;

  // Reload the current image to apply restored values on the canvas
  if (selectedIndex.value >= 0 && selectedIndex.value < images.value.length) {
    loadImageToCanvas(selectedIndex.value).catch(err => {
      console.error('clearAllEdits: failed to reload image after reset', err);
    });
  }
}

/**
 * Load image to canvas
 */
async function loadImageToCanvas(index: number): Promise<void> {
  const image: ImageMeta | undefined = images.value[index];
  if (!image || !mainCanvas.value) {
    console.log('loadImageToCanvas: no image or canvas', image, mainCanvas.value);
    return;
  }
  
  console.log('loadImageToCanvas: loading image', index, image.filename);
  
  try {
  
  // Initialize CanvasEngine if needed
  if (!canvasEngine) {
    canvasEngine = new CanvasEngine(mainCanvas.value);
    
    // Listen to canvas events
    canvasEngine.on('modified', () => {
      markDirty();
      updatePreview();
    });
    
      canvasEngine.on('zoomChanged', (data: any) => {
        zoom.value = data.zoom;
        updatePreview();
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
  
  // Load crop boxes FIRST (when image is not rotated, using top-left origin)
  // Bbox coordinates from metadata are for the rotated image, but we load them on unrotated image first
  if (image.bbox && image.bbox.length > 0) {
    // Try clone bbox to avoid mutation
    canvasEngine.loadCropBoxes(JSON.parse(JSON.stringify(image.bbox)));
  }
  
  // Apply rotation to canvas if needed - AFTER loading bbox
  // This will rotate both image and bbox together
  if (Math.abs(totalRotation) > 0.01) {
    applyRotation(totalRotation);
  }
  
  // Apply brightness/contrast if needed
  if (Math.abs(currentBrightness.value) > 0.1 || Math.abs(currentContrast.value) > 0.1) {
    applyBrightnessContrast();
  }
  
  // Update preview
  updatePreview();
  } catch (error) {
    console.error('Failed to load image to canvas:', error);
  }
}

/**
 * Select image
 */
async function selectImage(index: number): Promise<void> {
  console.log('selectImage: selecting', index);
  // Save current crop boxes before switching
  // Use getCropBoxesForOriginal() to get bbox in unrotated original image coordinates
  if (canvasEngine && currentImage.value) {
    currentImage.value.bbox = canvasEngine.getCropBoxesForOriginal();
  }
  
  selectedIndex.value = index;
  await loadImageToCanvas(index);
}

/**
 * Crop box management
 */
function addCropBox(): void {
  if (!canvasEngine) return;
  canvasEngine.addCropBox();
  markDirty();
}

function clearCrops() {
  if (!canvasEngine) return;
  canvasEngine.clear();
  previewUrl.value = null;
  markDirty();
}

async function updatePreview(): Promise<void> {
  if (!canvasEngine) return;

  const croppedDataUrl: string | null = await canvasEngine.exportCropBoxFromOriginal();

  if (croppedDataUrl) {
    previewUrl.value = croppedDataUrl;

    const originalCrops: CropBox[] = canvasEngine.getCropBoxes() || [];
    if (originalCrops.length > 0) {
      const crop = originalCrops[0];
      previewDimensions.value = {
        width: crop.w,
        height: crop.h,
        aspectRatio: calculateAspectRatio(crop.w, crop.h)
      };
    }
  }
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

/**
 * Khởi tạo Full Preview Modal
 */
async function initPreviewCanvas(): Promise<void> {
  if (!previewCanvas.value || !canvasEngine) return;
  
  try {
    // Use canvas-engine's export function (no args -> default png)
    const croppedDataUrl = await canvasEngine.exportCropBoxFromOriginal();
    
    if (!croppedDataUrl) return;
    
    if (!previewCanvasEngine) {
      previewCanvasEngine = new CanvasEngine(previewCanvas.value);
    }

    await previewCanvasEngine.loadImage(croppedDataUrl);
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
  // Update preview (coalesced) so crop preview reflects rotation
  schedulePreviewUpdate();
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
  // Update preview (coalesced) so crop preview reflects filters
  schedulePreviewUpdate();
}
 
// Coalesce preview updates using requestAnimationFrame to avoid expensive
// exportCropBoxFromOriginal() running on every tiny input event.
let _previewUpdateScheduled = false;
function schedulePreviewUpdate(): void {
  if (_previewUpdateScheduled) return;
  _previewUpdateScheduled = true;
  requestAnimationFrame(async () => {
    _previewUpdateScheduled = false;
    try {
      await updatePreview();
    } catch (err) {
      console.error('Failed to update preview:', err);
    }
  });
}

// Adjustment observer: batches rotation/brightness/contrast changes and applies
// them once per animation frame for smooth UI and minimal expensive exports.
let _adjustmentScheduled = false;
// Remember last applied values to avoid reapplying unchanged transforms
let _prevAppliedRotation = NaN;
let _prevAppliedBrightness = NaN;
let _prevAppliedContrast = NaN;
let _lastPreviewTs = 0;
const PREVIEW_THROTTLE_MS = 200;

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
    }

    if (brightnessChanged || contrastChanged) {
      canvasEngine.applyFilters({ brightness: bri / 100, contrast: con / 100 });
      _prevAppliedBrightness = bri;
      _prevAppliedContrast = con;
      // ensure preview reflects filters
      schedulePreviewUpdate();
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
      currentImage.value.bbox = boxes.length > 0 ? boxes : [];
    }
    
    const metadata = {
      session_id: projectId.value,
      mode: 'scan_document',
      images: images.value.map(img => ({
        id: img.id,
        filename: img.filename,  // Use filename instead of path
        rotation: img.rotation,
        deskew_angle: img.deskew_angle,  // Should be 0 after manual edit
        brightness: img.brightness,
        contrast: img.contrast,
        // Save bbox: if single box save as object, if multiple save as array, if none save as null
        bbox: img.bbox && img.bbox.length > 0 ? (img.bbox.length === 1 ? img.bbox[0] : img.bbox) : null
      }))
    };
    
    await axios.put(`/api/projects/${projectId.value}/metadata`, metadata);
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
  if (boxesToLoad && boxesToLoad.length > 0) {
    canvasEngine.loadCropBoxes(boxesToLoad);
  }

  // After reset to original, not dirty
  if (currentImage.value) currentImage.value._dirty = false;
  isDirty.value = images.value.some(img => !!img._dirty);

  updatePreview();
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
  loadProject();
  // nothing special on mount
});

onBeforeUnmount(() => {
  // Cleanup
  if (canvasEngine) {
    canvasEngine.destroy();
    canvasEngine = null;
  }
  // nothing special on unmount
});
</script>