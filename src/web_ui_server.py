"""
Web UI Server for Scan Editor
FastAPI backend serving REST API and static files
"""
from __future__ import annotations

import os
import base64
import json
import time
from typing import List, Dict, Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import fitz  # PyMuPDF
import cv2
import numpy as np
from PIL import Image
import io

# Configuration
# Auto-detect environment: Docker vs Local
def get_scan_dir():
    """Get scan output directory based on environment"""
    # Check if running in Docker
    if os.path.exists("/share/scan_out"):
        return "/share/scan_out"
    
    # Local development - relative to project root
    project_root = Path(__file__).parent.parent
    local_scan_dir = project_root / "scan_out"
    local_scan_dir.mkdir(exist_ok=True)
    return str(local_scan_dir)

SCAN_OUT_DIR = os.getenv("SCAN_OUTPUT_DIR", get_scan_dir())
WEB_UI_PORT = int(os.getenv("WEB_UI_PORT", "8099"))

app = FastAPI(title="Scan Editor API", version="1.0.0")

# CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Models
class CropBox(BaseModel):
    x: int
    y: int
    w: int
    h: int

class PageEdit(BaseModel):
    page: int
    crop: Optional[CropBox] = None
    rotate: Optional[int] = None
    brightness: Optional[float] = None
    contrast: Optional[float] = None

class EditRequest(BaseModel):
    filename: str
    pages: List[PageEdit]
    preview_width: int = 800

class ProjectMetadata(BaseModel):
    """Project metadata for scan editing"""
    project_id: str
    original_pdf: str
    created: int
    updated: int
    images: List[Dict]  # List of image metadata
    layout: Optional[Dict] = None  # Layout settings


# API Endpoints

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "service": "scan-editor"}


@app.get("/api/projects")
async def list_projects():
    """List all PDF projects (generated scans) with metadata"""
    if not os.path.exists(SCAN_OUT_DIR):
        return {"projects": []}
    
    projects = []
    for filename in sorted(os.listdir(SCAN_OUT_DIR), reverse=True):
        if filename.endswith('.pdf') and not filename.endswith('_mono.pdf'):
            filepath = os.path.join(SCAN_OUT_DIR, filename)
            stat = os.stat(filepath)
            
            # Get PDF info
            try:
                doc = fitz.open(filepath)
                pages_count = len(doc)
                
                # Get first page as thumbnail
                first_page = doc[0]
                pix = first_page.get_pixmap(dpi=72)
                thumb_bytes = pix.tobytes("png")
                thumb_b64 = base64.b64encode(thumb_bytes).decode()
                
                doc.close()
                
                # Check for metadata file
                base_name = os.path.splitext(filename)[0]
                metadata_path = os.path.join(SCAN_OUT_DIR, f"{base_name}.json")
                has_metadata = os.path.exists(metadata_path)
                
                # Extract mode from filename (test_scan_document, test_card_2in1, etc)
                mode = "unknown"
                if "scan_document" in filename:
                    mode = "scan_document"
                elif "card" in filename or "2in1" in filename:
                    mode = "card_2in1"
                elif "duplex" in filename:
                    mode = "scan_duplex"
                
                projects.append({
                    "id": base_name,
                    "filename": filename,
                    "mode": mode,
                    "pages": pages_count,
                    "size": stat.st_size,
                    "size_mb": round(stat.st_size / 1024 / 1024, 2),
                    "created": int(stat.st_ctime),
                    "updated": int(stat.st_mtime),
                    "has_metadata": has_metadata,
                    "thumbnail": f"data:image/png;base64,{thumb_b64}"
                })
            except Exception as e:
                print(f"Error processing {filename}: {e}")
                continue
    
    return {"projects": projects}


@app.get("/api/projects/{project_id}/images")
async def get_project_images(project_id: str):
    """Extract all images from PDF project"""
    pdf_path = os.path.join(SCAN_OUT_DIR, f"{project_id}.pdf")
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="Project not found")
    
    try:
        doc = fitz.open(pdf_path)
        images = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            
            # Get page as image
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")
            img_b64 = base64.b64encode(img_bytes).decode()
            
            # Try to detect individual images on page (for scan_document mode)
            # For now, treat each page as one image
            images.append({
                "id": f"img_{page_num}",
                "page": page_num,
                "width": int(page.rect.width),
                "height": int(page.rect.height),
                "thumbnail": f"data:image/png;base64,{img_b64}",
                "url": f"/api/scan/{project_id}.pdf/page/{page_num}?size=medium"
            })
        
        doc.close()
        return {"images": images}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/projects/{project_id}/metadata")
async def get_project_metadata(project_id: str):
    """Get project metadata from pipeline-generated JSON"""
    metadata_path = os.path.join(SCAN_OUT_DIR, f"{project_id}.json")
    
    if not os.path.exists(metadata_path):
        raise HTTPException(status_code=404, detail="Metadata not found")
    
    try:
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        # Metadata now stores simple filenames (no paths)
        # Frontend will use /api/images/{project_id}/{filename} to access
        if 'images' in metadata:
            for img in metadata['images']:
                # Ensure default values
                img.setdefault('brightness', 1.0)
                img.setdefault('contrast', 1.0)
                img.setdefault('rotation', 0)
                img.setdefault('deskew_angle', 0.0)
        
        return metadata
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load metadata: {str(e)}")


@app.get("/api/images/{filename}")
async def get_project_image(filename: str, project_id: str, size: str = "medium", request: Request = None):
    """Serve image with smart resizing and caching
    
    Strategy:
    - Original images stay in scan_inbox (300-600 DPI, several MB each)
    - Generate thumbnails on-demand with disk caching
    - Cache in scan_out/.thumbnails/{size}/{filename}
    
    Sizes:
    - thumbnail: 200px width (for grid view)
    - medium: 800px width (for editor preview)
    - large: 1600px width (for detail view)
    - original: Full resolution (fallback)
    
    Security:
    - Validates project_id exists
    - Prevents directory traversal
    - Only serves files referenced in project metadata
    
    Performance:
    - Disk cache for generated thumbnails
    - ETags for browser caching
    - Progressive JPEG for faster loading
    
    Args:
        filename: Image filename
        project_id: Project ID
        size: Image size (thumbnail/medium/large/original)
    """
    # Security: Prevent directory traversal
    if '..' in filename or filename.startswith('/') or '\\' in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    # Security: Validate project exists and get source path
    project_json = os.path.join(SCAN_OUT_DIR, f"{project_id}.json")
    if not os.path.exists(project_json):
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Load metadata to get source_path
    try:
        with open(project_json, 'r') as f:
            metadata = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load metadata: {str(e)}")
    
    # Find image in metadata
    img_meta = next((img for img in metadata.get('images', []) 
                    if img.get('filename') == filename or img.get('source_file') == filename), None)
    
    if not img_meta or 'source_path' not in img_meta:
        raise HTTPException(status_code=404, detail=f"Image not in project: {filename}")
    
    source_path = img_meta['source_path']
    
    # Security: Verify source file exists
    if not os.path.exists(source_path):
        raise HTTPException(status_code=404, detail=f"Source image not found: {filename}")
    
    # Security: Check file size of original (limit 50MB)
    source_size = os.path.getsize(source_path)
    if source_size > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Source file too large")
    
    # Size configuration
    size_config = {
        'thumbnail': 200,
        'medium': 800,
        'large': 1600,
        'original': None
    }
    
    target_width = size_config.get(size)
    if target_width is None and size != 'original':
        raise HTTPException(status_code=400, detail="Invalid size parameter")
    
    # Original size: serve source file directly
    if size == 'original':
        file_stat = os.stat(source_path)
        etag = f'"{file_stat.st_mtime}-{file_stat.st_size}"'
        last_modified = time.strftime('%a, %d %b %Y %H:%M:%S GMT', time.gmtime(file_stat.st_mtime))
        
        # Check If-None-Match
        if request and request.headers.get('if-none-match') == etag:
            return JSONResponse(status_code=304, content=None)
        
        return FileResponse(
            source_path,
            media_type="image/jpeg",
            headers={
                'ETag': etag,
                'Last-Modified': last_modified,
                'Cache-Control': 'public, max-age=31536000, immutable',
            }
        )
    
    # Thumbnail: check cache first
    cache_dir = os.path.join(SCAN_OUT_DIR, '.thumbnails', size)
    os.makedirs(cache_dir, exist_ok=True)
    
    cache_path = os.path.join(cache_dir, filename)
    
    # Generate thumbnail if not cached or source is newer
    source_mtime = os.path.getmtime(source_path)
    needs_generate = True
    
    if os.path.exists(cache_path):
        cache_mtime = os.path.getmtime(cache_path)
        if cache_mtime >= source_mtime:
            needs_generate = False
    
    if needs_generate:
        try:
            # Generate thumbnail using PIL
            from PIL import Image as PILImage
            
            img = PILImage.open(source_path)
            
            # Calculate resize dimensions (maintain aspect ratio)
            aspect_ratio = img.height / img.width
            new_width = target_width
            new_height = int(target_width * aspect_ratio)
            
            # Resize with high quality
            img_resized = img.resize((new_width, new_height), PILImage.Resampling.LANCZOS)
            
            # Save as progressive JPEG with optimization
            img_resized.save(
                cache_path,
                'JPEG',
                quality=85,
                optimize=True,
                progressive=True
            )
            
            print(f"🖼️  Generated {size} thumbnail: {filename} ({source_size // 1024}KB → {os.path.getsize(cache_path) // 1024}KB)")
            
        except Exception as e:
            print(f"⚠️  Thumbnail generation failed for {filename}: {e}")
            # Fallback to original
            cache_path = source_path
    
    # Serve cached thumbnail
    file_stat = os.stat(cache_path)
    etag = f'"{file_stat.st_mtime}-{file_stat.st_size}-{size}"'
    last_modified = time.strftime('%a, %d %b %Y %H:%M:%S GMT', time.gmtime(file_stat.st_mtime))
    
    # Check If-None-Match
    if request and request.headers.get('if-none-match') == etag:
        return JSONResponse(status_code=304, content=None)
    
    return FileResponse(
        cache_path,
        media_type="image/jpeg",
        headers={
            'ETag': etag,
            'Last-Modified': last_modified,
            'Cache-Control': 'public, max-age=31536000, immutable',
        }
    )


@app.put("/api/projects/{project_id}/metadata")
async def update_project_metadata(project_id: str, metadata: ProjectMetadata):
    """Update project metadata"""
    metadata_path = os.path.join(SCAN_OUT_DIR, f"{project_id}.json")
    
    try:
        metadata_dict = metadata.dict()
        metadata_dict["updated"] = int(time.time())
        
        with open(metadata_path, 'w') as f:
            json.dump(metadata_dict, f, indent=2)
        
        return {"status": "success", "updated": metadata_dict["updated"]}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/scans")
async def list_scans():
    """List all PDF files in scan_out directory"""
    if not os.path.exists(SCAN_OUT_DIR):
        return {"scans": []}
    
    scans = []
    for filename in sorted(os.listdir(SCAN_OUT_DIR), reverse=True):
        if filename.endswith('.pdf'):
            filepath = os.path.join(SCAN_OUT_DIR, filename)
            stat = os.stat(filepath)
            
            # Get PDF info
            try:
                doc = fitz.open(filepath)
                pages = len(doc)
                doc.close()
            except:
                pages = 0
            
            scans.append({
                "filename": filename,
                "path": filepath,
                "size": stat.st_size,
                "size_mb": round(stat.st_size / 1024 / 1024, 2),
                "created": int(stat.st_ctime),
                "pages": pages
            })
    
    return {"scans": scans}


@app.get("/api/scan/{filename}/info")
async def get_scan_info(filename: str):
    """Get PDF metadata"""
    filepath = os.path.join(SCAN_OUT_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        doc = fitz.open(filepath)
        
        # Get first page dimensions
        page = doc[0]
        width = int(page.rect.width)
        height = int(page.rect.height)
        
        info = {
            "filename": filename,
            "pages": len(doc),
            "width": width,
            "height": height,
            "metadata": doc.metadata
        }
        
        doc.close()
        return info
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/scan/{filename}/page/{page_num}")
async def get_page_image(filename: str, page_num: int, size: str = "medium"):
    """
    Extract page as image with specified size
    size: small (400px), medium (800px), large (1200px)
    """
    filepath = os.path.join(SCAN_OUT_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        doc = fitz.open(filepath)
        
        if page_num < 0 or page_num >= len(doc):
            raise HTTPException(status_code=400, detail="Invalid page number")
        
        page = doc[page_num]
        
        # Determine DPI based on size
        if size == "small":
            dpi = 72  # ~400px width for A4
        elif size == "large":
            dpi = 200  # ~1600px width
        else:  # medium
            dpi = 150  # ~1200px width
        
        # Render page as image
        pix = page.get_pixmap(dpi=dpi)
        img_data = pix.tobytes("png")
        
        doc.close()
        
        return StreamingResponse(
            io.BytesIO(img_data),
            media_type="image/png",
            headers={"Cache-Control": "max-age=3600"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/scan/{filename}/pages")
async def get_all_pages(filename: str, size: str = "small"):
    """Get all pages as base64 images (for thumbnail gallery)"""
    filepath = os.path.join(SCAN_OUT_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        doc = fitz.open(filepath)
        pages = []
        
        dpi = 72 if size == "small" else 100
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(dpi=dpi)
            img_data = pix.tobytes("png")
            b64 = base64.b64encode(img_data).decode()
            
            pages.append({
                "page": page_num,
                "image": f"data:image/png;base64,{b64}",
                "width": pix.width,
                "height": pix.height
            })
        
        doc.close()
        return {"pages": pages}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/edit")
async def apply_edits(request: EditRequest):
    """Apply edits to PDF and generate new file"""
    filepath = os.path.join(SCAN_OUT_DIR, request.filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        # Extract images from PDF
        doc = fitz.open(filepath)
        
        # Get original dimensions from first page
        first_page = doc[0]
        original_width = int(first_page.rect.width)
        
        # Calculate scale factor
        scale = original_width / request.preview_width
        
        # Process each page
        processed_images = []
        
        for page_edit in request.pages:
            page = doc[page_edit.page]
            
            # Render at high DPI for quality
            pix = page.get_pixmap(dpi=300)
            img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            
            # Convert to BGR for OpenCV
            if pix.n == 4:  # RGBA
                img = cv2.cvtColor(img_array, cv2.COLOR_RGBA2BGR)
            else:  # RGB
                img = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
            
            # Apply crop if specified
            if page_edit.crop:
                crop = page_edit.crop
                # Scale coordinates to original resolution
                x = int(crop.x * scale * (300/72))  # Adjust for DPI
                y = int(crop.y * scale * (300/72))
                w = int(crop.w * scale * (300/72))
                h = int(crop.h * scale * (300/72))
                
                # Ensure bounds
                x = max(0, min(x, img.shape[1]))
                y = max(0, min(y, img.shape[0]))
                w = min(w, img.shape[1] - x)
                h = min(h, img.shape[0] - y)
                
                img = img[y:y+h, x:x+w]
            
            # Apply rotation if specified
            if page_edit.rotate:
                if page_edit.rotate == 90:
                    img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
                elif page_edit.rotate == 180:
                    img = cv2.rotate(img, cv2.ROTATE_180)
                elif page_edit.rotate == 270:
                    img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
            
            # Apply brightness/contrast if specified
            if page_edit.brightness or page_edit.contrast:
                alpha = page_edit.contrast or 1.0
                beta = int((page_edit.brightness or 1.0 - 1.0) * 100)
                img = cv2.convertScaleAbs(img, alpha=alpha, beta=beta)
            
            processed_images.append(img)
        
        doc.close()
        
        # Generate new PDF
        base_name = os.path.splitext(request.filename)[0]
        output_filename = f"{base_name}_edited.pdf"
        output_path = os.path.join(SCAN_OUT_DIR, output_filename)
        
        # Convert images to PIL and save as PDF
        pil_images = []
        for img in processed_images:
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(img_rgb)
            pil_images.append(pil_img)
        
        if pil_images:
            pil_images[0].save(
                output_path,
                save_all=True,
                append_images=pil_images[1:] if len(pil_images) > 1 else [],
                resolution=300.0,
                quality=95
            )
        
        # Save metadata for bbox info
        metadata = {
            "original_file": request.filename,
            "pages": [
                {
                    "page": edit.page,
                    "crop": edit.crop.dict() if edit.crop else None,
                    "rotate": edit.rotate,
                    "brightness": edit.brightness,
                    "contrast": edit.contrast
                }
                for edit in request.pages
            ],
            "preview_width": request.preview_width,
            "timestamp": int(time.time())
        }
        
        metadata_path = os.path.join(SCAN_OUT_DIR, f"{base_name}_edited.json")
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        return {
            "status": "success",
            "file": output_filename,
            "pages_processed": len(processed_images),
            "metadata_saved": True
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/scan/{filename}/metadata")
async def get_scan_metadata(filename: str):
    """Get metadata for edited scan (bbox info, etc)"""
    # Remove .pdf extension and add .json
    base_name = os.path.splitext(filename)[0]
    metadata_path = os.path.join(SCAN_OUT_DIR, f"{base_name}.json")
    
    if not os.path.exists(metadata_path):
        return {"has_metadata": False}
    
    try:
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
        return {
            "has_metadata": True,
            **metadata
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/download/{filename}")
async def download_file(filename: str):
    """Download PDF file"""
    filepath = os.path.join(SCAN_OUT_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        filepath,
        media_type="application/pdf",
        filename=filename
    )


@app.delete("/api/scan/{filename}")
async def delete_scan(filename: str):
    """Delete PDF file"""
    filepath = os.path.join(SCAN_OUT_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        os.remove(filepath)
        return {"status": "deleted", "filename": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/projects/{project_id}/generate")
async def generate_pdf_with_progress(
    project_id: str,
    request: Request
):
    """
    Generate PDF from metadata with Server-Sent Events for real-time progress.
    
    Expects JSON body with:
    - quality: 'low' (150 DPI), 'medium' (200 DPI), 'high' (300 DPI)
    - paper_size: 'a4_fit', 'a4_ratio', 'original'
    - filename: Optional custom filename
    
    Returns SSE stream with progress updates.
    """
    import asyncio
    from agent.transform_service import apply_metadata_transforms
    from agent.pdf_generator import save_pdf_scan_document_fast, save_pdf_scan_document_mono_fast
    from agent.layout_engine import layout_items_by_orientation
    from reportlab.lib.pagesizes import A4
    
    # Parse request body
    try:
        body = await request.json()
        quality = body.get('quality', 'medium')
        paper_size = body.get('paper_size', 'a4_fit')
        filename = body.get('filename', None)
    except:
        quality = 'medium'
        paper_size = 'a4_fit'
        filename = None
    
    async def generate():
        try:
            # Stage 1: Load metadata (0-20%)
            yield f"data: {json.dumps({'progress': 0, 'stage': 'loading', 'message': 'Loading project metadata...'})}\n\n"
            await asyncio.sleep(0.1)
            
            metadata_path = os.path.join(SCAN_OUT_DIR, f"{project_id}.json")
            if not os.path.exists(metadata_path):
                yield f"data: {json.dumps({'error': f'Project {project_id} not found'})}\n\n"
                return
            
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            images = metadata.get('images', [])
            if not images:
                yield f"data: {json.dumps({'error': 'No images in project'})}\n\n"
                return
            
            yield f"data: {json.dumps({'progress': 10, 'stage': 'loading', 'message': f'Loaded {len(images)} images'})}\n\n"
            await asyncio.sleep(0.1)
            
            # Determine DPI based on quality
            dpi_map = {'low': 150, 'medium': 200, 'high': 300}
            target_dpi = dpi_map.get(quality, 200)
            
            # Stage 2: Apply transformations (20-50%)
            yield f"data: {json.dumps({'progress': 20, 'stage': 'transform', 'message': 'Applying image transformations...'})}\n\n"
            await asyncio.sleep(0.1)
            
            transformed_items = []
            for i, img_meta in enumerate(images):
                # Progress: 20% + (i / total * 30%)
                progress = 20 + int((i / len(images)) * 30)
                yield f"data: {json.dumps({'progress': progress, 'stage': 'transform', 'message': f'Transforming image {i+1}/{len(images)}...'})}\n\n"
                await asyncio.sleep(0.05)
                
                try:
                    # Get filename and construct full path
                    filename = img_meta.get('filename') or img_meta.get('source_file')
                    if not filename:
                        continue
                    
                    img_path = os.path.join(SCAN_OUT_DIR, filename)
                    if not os.path.exists(img_path):
                        yield f"data: {json.dumps({'warning': f'Image not found: {filename}'})}\n\n"
                        continue
                    
                    # Apply all transformations
                    transformed_img = apply_metadata_transforms(
                        img_path,
                        img_meta,
                        apply_bbox_crop=True,
                        target_dpi=target_dpi
                    )
                    
                    # Build doc_item: (span, pos, img, dpi)
                    span = 'single'
                    pos = (0, 0)
                    
                    transformed_items.append((span, pos, transformed_img, target_dpi))
                
                except Exception as e:
                    yield f"data: {json.dumps({'warning': f'Failed to transform image {i+1}: {str(e)}'})}\n\n"
                    continue
            
            if not transformed_items:
                yield f"data: {json.dumps({'error': 'No images could be transformed'})}\n\n"
                return
            
            yield f"data: {json.dumps({'progress': 50, 'stage': 'transform', 'message': f'Transformed {len(transformed_items)} images'})}\n\n"
            await asyncio.sleep(0.1)
            
            # Stage 3: Render PDF (50-90%)
            yield f"data: {json.dumps({'progress': 50, 'stage': 'render', 'message': 'Laying out pages...'})}\n\n"
            await asyncio.sleep(0.1)
            
            # Layout items by orientation
            pages = layout_items_by_orientation(transformed_items)
            
            yield f"data: {json.dumps({'progress': 60, 'stage': 'render', 'message': f'Rendering {len(pages)} pages...'})}\n\n"
            await asyncio.sleep(0.1)
            
            # Determine output filename
            if filename:
                base_filename = filename
            else:
                base_filename = project_id
            
            # Generate color PDF
            output_color = os.path.join(SCAN_OUT_DIR, f"{base_filename}_color.pdf")
            output_mono = os.path.join(SCAN_OUT_DIR, f"{base_filename}_mono.pdf")
            
            yield f"data: {json.dumps({'progress': 70, 'stage': 'render', 'message': 'Generating color PDF...'})}\n\n"
            await asyncio.sleep(0.1)
            
            # Run PDF generation in thread pool (blocking I/O)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                save_pdf_scan_document_fast,
                pages,
                output_color,
                A4
            )
            
            yield f"data: {json.dumps({'progress': 80, 'stage': 'render', 'message': 'Generating monochrome PDF...'})}\n\n"
            await asyncio.sleep(0.1)
            
            await loop.run_in_executor(
                None,
                save_pdf_scan_document_mono_fast,
                pages,
                output_mono,
                A4
            )
            
            # Stage 4: Save and complete (90-100%)
            yield f"data: {json.dumps({'progress': 90, 'stage': 'save', 'message': 'Finalizing PDF files...'})}\n\n"
            await asyncio.sleep(0.1)
            
            # Get file sizes
            color_size = os.path.getsize(output_color) if os.path.exists(output_color) else 0
            mono_size = os.path.getsize(output_mono) if os.path.exists(output_mono) else 0
            
            yield f"data: {json.dumps({'progress': 100, 'stage': 'complete', 'message': 'PDF generation complete!', 'files': [{'path': output_color, 'size': color_size, 'type': 'color'}, {'path': output_mono, 'size': mono_size, 'type': 'monochrome'}]})}\n\n"
        
        except Exception as e:
            yield f"data: {json.dumps({'error': f'PDF generation failed: {str(e)}'})}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")


# Serve static files (Vue app)
# Mount after API routes to avoid conflicts
web_ui_dist = Path(__file__).parent.parent / "web_ui" / "dist"
if web_ui_dist.exists():
    app.mount("/", StaticFiles(directory=str(web_ui_dist), html=True), name="static")
else:
    print(f"⚠️  Web UI dist not found at {web_ui_dist}")
    print("💡 Run: cd web_ui && npm run build")


if __name__ == "__main__":
    import uvicorn
    print(f"🚀 Starting Web UI Server...")
    print(f"📁 Scan directory: {SCAN_OUT_DIR}")
    print(f"🌐 Server: http://localhost:{WEB_UI_PORT}")
    print(f"📊 API docs: http://localhost:{WEB_UI_PORT}/docs")
    uvicorn.run(app, host="0.0.0.0", port=WEB_UI_PORT)
