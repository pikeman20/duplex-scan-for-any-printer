# Model Dependencies for PrinterDuplexScanForCheapPrint

## Overview
The image processing pipeline in PrinterDuplexScanForCheapPrint relies on several ONNX model files for advanced features like background removal, depth estimation, and focus matting. These models are stored in the `./checkpoints/` directory and are validated during startup by the ConfigValidator.

## Required Model Files

### 1. Background Removal Models
- **isnet.onnx** - IS-Net model for accurate foreground/background segmentation
  - Used by: `withoutbg.OpenSourceModel` in `image_processing.py`
  - Purpose: Precise document boundary detection and background removal
  - Size: ~48 MB

### 2. Depth Estimation Models
- **depth_anything_v2_vits_slim.onnx** - Depth Anything V2 model (SwinTiny variant)
  - Used by: Depth estimation features in image processing
  - Purpose: Understanding spatial relationships in scanned documents
  - Size: ~100 MB

### 3. Focus Matting Models
- **focus_matting_1.0.0.onnx** - Focus matting model
  - Used by: Edge refinement in document processing
  - Purpose: Improving edge quality after segmentation
  - Size: ~25 MB

- **focus_refiner_1.0.0.onnx** - Focus refiner model
  - Used by: Final refinement of document boundaries
  - Purpose: Enhancing precision of detected document edges
  - Size: ~25 MB

## Validation Process

The `ConfigValidator.validate_all()` method in `src/agent/config_validator.py` performs the following checks:

1. **File Existence**: Verifies all four model files exist in `./checkpoints/`
2. **File Size**: Performs basic size sanity checks (though specific thresholds may vary)
3. **Accessibility**: Ensures files are readable by the application process

If any model file is missing or inaccessible:
- Validation will fail with descriptive error messages
- Advanced image processing features (background removal, depth estimation) may be degraded or unavailable
- Basic functionality (orientation detection, deskewing, PDF generation) remains operational

## Installation Instructions

### Option 1: Automatic Download (Recommended)
The project may include scripts or documentation for automatically downloading the required models. Check for:
- `download_models.sh` or similar scripts
- Documentation in `DEPLOYMENT.md` or `README_ADDON.md`

### Option 2: Manual Download
If automatic download is not available:

1. Create the checkpoints directory (if it doesn't exist):
   ```bash
   mkdir -p ./checkpoints
   ```

2. Download each model file to `./checkpoints/`:
   - isnet.onnx
   - depth_anything_v2_vits_slim.onnx
   - focus_matting_1.0.0.onnx
   - focus_refiner_1.0.0.onnx

3. Verify file placement:
   ```bash
   ls -la ./checkpoints/
   # Should show all four .onnx files
   ```

## Fallback Behavior

When model files are missing or unavailable:

### Background Removal (`crop_document_v2` in image_processing.py):
- Falls back to returning the original image unprocessed
- May still apply basic cropping based on image boundaries
- Document detection accuracy significantly reduced

### Depth Estimation Features:
- Features requiring depth information will be skipped or use default values
- May affect advanced layout decisions in complex document scenarios

### Focus Matting/Refinement:
- Edge refinement steps will be skipped
- Document boundaries may appear less precise but functional

## Performance Notes

### Memory Usage
- Each model consumes RAM when loaded
- Consider system memory constraints, especially on low-power devices (Raspberry Pi, etc.)
- Models are loaded on-demand and can be explicitly unloaded to conserve memory

### Loading Time
- Initial model loading may take several seconds per model
- Subsequent inferences are faster once models are loaded
- Consider pre-loading models during application startup for better user experience

## Troubleshooting

### Common Issues
1. **"Model file not found" errors**
   - Verify files exist in `./checkpoints/` directory
   - Check file permissions (should be readable by application user)

2. **Invalid model format errors**
   - Ensure downloaded files are complete and not corrupted
   - Verify you have the correct model versions

3. **Out-of-memory errors**
   - Reduce concurrent processing workers if available
   - Consider using model quantization or smaller variants if supported
   - Ensure sufficient swap space is available

### Verification
To verify models are working correctly:
1. Check application logs for successful model loading messages
2. Test with sample documents to verify background removal is functioning
3. Monitor memory usage during image processing operations

## Maintenance

### Model Updates
- Periodically check for newer versions of these models
- Updated models may offer improved accuracy or performance
- Maintain backward compatibility when updating

### Security
- Only download models from trusted sources
- Verify file hashes/signatures when available
- Keep model files outside of publicly accessible web directories

## References
- IS-Net: https://github.com/xuebinqin/U-2-Net
- Depth Anything V2: https://github.com/DepthAnything/Depth-Anything-V2
- Focus Matting/Refining: Refer to withoutbg library documentation