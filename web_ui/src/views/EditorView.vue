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
}

const emit = defineEmits(['back']);
const editorStore = useEditorStore();

// State
const images: Ref<ImageMeta[]> = ref([] as ImageMeta[]);
const selectedIndex = ref<number>(0);
const mainCanvas = ref<HTMLCanvasElement | null>(null);
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
      bbox: img.bbox ? (Array.isArray(img.bbox) ? img.bbox : [img.bbox]) : []
    } as ImageMeta));
    
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
  } else {
    console.error('updatePreview: no cropped data URL');
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
}

/**
 * Brightness/Contrast adjustment handlers
 */
function startBrightnessAdjust() {
  isAdjusting = true;
}

function onBrightnessInput() {
  if (isAdjusting) {
    applyBrightnessContrast();
  }
}

function finishBrightnessAdjust() {
  isAdjusting = false;
  markDirty();
}

function startContrastAdjust() {
  isAdjusting = true;
}

function onContrastInput() {
  if (isAdjusting) {
    applyBrightnessContrast();
  }
}

function finishContrastAdjust() {
  isAdjusting = false;
  markDirty();
}

/**
 * Handle rotation adjustment
 */
function handleAdjustment(): void {
  applyRotation(currentRotation.value);
  markDirty();
}

/**
 * Handle rotation change
 */
watch(currentRotation, () => {
  if (currentImage.value) {
    applyRotation(currentRotation.value);
    markDirty();
  }
});

/**
 * Reset adjustments
 */
function resetAdjustments() {
  currentRotation.value = 0;
  currentBrightness.value = 0;
  currentContrast.value = 0;
  
  applyRotation(0);
  applyBrightnessContrast();
  
  markDirty();
}

/**
 * Mark as dirty
 */
function markDirty(): void {
  isDirty.value = true;
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

  if (currentImage.value && currentImage.value.bbox && currentImage.value.bbox.length > 0) {
    canvasEngine.clear();
    canvasEngine.loadCropBoxes(currentImage.value.bbox);
  } else {
    canvasEngine.clear();
  }

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
});

onBeforeUnmount(() => {
  // Cleanup
  if (canvasEngine) {
    canvasEngine.destroy();
    canvasEngine = null;
  }
});
</script>