"""
Metadata generation utilities for scan projects
"""
from __future__ import annotations

import json
import time
from typing import List, Tuple, Dict, Any
from PIL import Image


def generate_scan_document_metadata(
    session_id: str,
    doc_items: List[Tuple[str, Tuple[int, int], Image.Image, float, int, float, str]],
    pages: List[List[Tuple[str, Tuple[int, int], Image.Image, float]]],
    output_dir: str
) -> str:
    """
    Generate metadata JSON for scan_document project.
    
    Args:
        session_id: Session/project ID
        doc_items: List of (span, bbox, image, dpi, rotation_angle, deskew_angle, filename) tuples
        pages: Layout result from layout_documents_smart
        output_dir: Output directory for metadata file
    
    Returns:
        Path to metadata JSON file
    """
    metadata = {
        "project_id": session_id,
        "original_pdf": f"{session_id}.pdf",
        "created": int(time.time()),
        "updated": int(time.time()),
        "mode": "scan_document",
        "images": [],
        "layout": {
            "page_size": "A4",
            "orientation": "portrait",
            "margin": 10,
            "positions": []
        }
    }
    
    # Build image metadata
    img_id_map = {}  # Map filename to img_id
    for idx, (span, bbox, img, dpi, rotation, deskew, filename) in enumerate(doc_items):
        img_id = f"img_{idx}"
        img_id_map[filename] = img_id
        
        # Store source path - images remain in scan_inbox (not copied)
        # Web UI will request thumbnails via /api/images/{filename}?project_id={id}&size={size}
        import os
        
        simple_filename = os.path.basename(filename)
        
        metadata["images"].append({
            "id": img_id,
            "source_file": simple_filename,
            "filename": simple_filename,  # Simple filename for API access
            "source_path": filename,  # Full path in scan_inbox for serving
            "bbox": {
                "x": bbox[0],
                "y": bbox[1],
                "w": img.width,
                "h": img.height
            },
            "rotation": rotation,  # Actual rotation applied (0 or 180)
            "deskew_angle": round(deskew, 2),  # Actual deskew angle detected and applied
            "brightness": 1.0,
            "contrast": 1.0,
            "scan_dpi": dpi,
            "order": idx
        })
    
    # Build layout positions from pages
    page_num = 0
    for page_items in pages:
        for span, (draw_x, draw_y), img, scan_dpi in page_items:
            # Find matching image by comparing dimensions
            matching_img_id = None
            for item_idx, (item_span, item_bbox, item_img, item_dpi, item_rot, item_deskew, item_filename) in enumerate(doc_items):
                if item_img.width == img.width and item_img.height == img.height:
                    matching_img_id = f"img_{item_idx}"
                    break
            
            if matching_img_id:
                metadata["layout"]["positions"].append({
                    "img_id": matching_img_id,
                    "page": page_num,
                    "x": draw_x,
                    "y": draw_y,
                    "width": img.width,
                    "height": img.height,
                    "span": span
                })
        page_num += 1
    
    # Save metadata
    import os
    metadata_path = os.path.join(output_dir, f"{session_id}.json")
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"💾 Metadata saved: {metadata_path}")
    return metadata_path


def generate_card_2in1_metadata(
    session_id: str,
    images: List[Image.Image],
    pages: List[List[Tuple[Tuple[int, int], Image.Image]]],
    deskew_angles: List[float],
    output_dir: str
) -> str:
    """
    Generate metadata JSON for card_2in1 project.
    
    Args:
        session_id: Session/project ID
        images: List of card images
        pages: Layout result from layout_items_by_orientation
        deskew_angles: List of deskew angles for each image
        output_dir: Output directory for metadata file
    
    Returns:
        Path to metadata JSON file
    """
    metadata = {
        "project_id": session_id,
        "original_pdf": f"{session_id}.pdf",
        "created": int(time.time()),
        "updated": int(time.time()),
        "mode": "card_2in1",
        "images": [],
        "layout": {
            "page_size": "A4",
            "orientation": "portrait",
            "margin": 10,
            "grid": "2x2",
            "positions": []
        }
    }
    
    # Build image metadata
    import os
    for idx, img in enumerate(images):
        # For card_2in1, images are cropped from scans, path will be in output_dir
        image_filename = f"card_{idx}.jpg"
        image_path = os.path.join(output_dir, image_filename)
        deskew_angle = deskew_angles[idx] if idx < len(deskew_angles) else 0.0
        
        metadata["images"].append({
            "id": f"img_{idx}",
            "source_index": idx,
            "path": image_path,
            "width": img.width,
            "height": img.height,
            "rotation": 0,  # card_2in1 doesn't use batch rotation
            "deskew_angle": round(deskew_angle, 2),  # Actual deskew angle detected and applied
            "order": idx
        })
    
    # Build layout positions from pages
    page_num = 0
    for page_items in pages:
        for quadrant, img in page_items:
            # Find matching image
            matching_idx = None
            for idx, orig_img in enumerate(images):
                if orig_img.width == img.width and orig_img.height == img.height:
                    matching_idx = idx
                    break
            
            if matching_idx is not None:
                metadata["layout"]["positions"].append({
                    "img_id": f"img_{matching_idx}",
                    "page": page_num,
                    "quadrant": quadrant,
                    "width": img.width,
                    "height": img.height
                })
        page_num += 1
    
    # Save metadata
    import os
    metadata_path = os.path.join(output_dir, f"{session_id}.json")
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"💾 Metadata saved: {metadata_path}")
    return metadata_path
