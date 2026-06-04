"""Image analysis tools: OCR, object detection, visual understanding."""

import base64
import io
import logging
import mimetypes
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import tool_registry as registry
from security_utils import SecurePathValidator, sanitize_user_input

logger = logging.getLogger(__name__)

# Global security instance
_path_validator = SecurePathValidator()

# ── Image Processing Dependencies ──────────────────────────────────────────

try:
    from PIL import Image, ImageEnhance, ImageFilter
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logger.warning("PIL/Pillow not available. Install with: pip install pillow")

try:
    import cv2
    import numpy as np
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    logger.warning("OpenCV not available. Install with: pip install opencv-python")

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    logger.warning("Tesseract OCR not available. Install with: pip install pytesseract")

# Lazy loading for EasyOCR to improve startup performance
EASYOCR_AVAILABLE = None
_easyocr_reader = None

def _get_easyocr():
    """Lazy load EasyOCR to improve startup performance."""
    global EASYOCR_AVAILABLE, _easyocr_reader
    
    if EASYOCR_AVAILABLE is None:
        try:
            import easyocr
            EASYOCR_AVAILABLE = True
        except ImportError:
            EASYOCR_AVAILABLE = False
            logger.warning("EasyOCR not available. Install with: pip install easyocr")
        except Exception as e:
            EASYOCR_AVAILABLE = False
            logger.warning("EasyOCR not available due to system issue: %s", e)
    
    if EASYOCR_AVAILABLE and _easyocr_reader is None:
        import easyocr
        _easyocr_reader = easyocr.Reader(['en'])
    
    return _easyocr_reader if EASYOCR_AVAILABLE else None

# ── Helper Functions ─────────────────────────────────────────────────────────

def _validate_image_path(path: str) -> Path:
    """Validate and secure image file path."""
    try:
        safe_path = _path_validator.validate_path(path)
        
        # Check if file exists
        if not safe_path.exists():
            raise FileNotFoundError(f"Image file not found: {path}")
        
        # Validate file extension
        valid_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'}
        if safe_path.suffix.lower() not in valid_extensions:
            raise ValueError(f"Unsupported image format: {safe_path.suffix}")
        
        return safe_path
    except Exception as e:
        logger.error("Image path validation failed: %s", e)
        raise

def _load_image_pil(path: Union[str, Path]) -> Image.Image:
    """Load image using PIL."""
    if not PIL_AVAILABLE:
        raise RuntimeError("PIL/Pillow is required for image processing")
    
    try:
        img = Image.open(path)
        # Convert to RGB if needed
        if img.mode != 'RGB':
            img = img.convert('RGB')
        return img
    except Exception as e:
        logger.error("Failed to load image with PIL: %s", e)
        raise

def _load_image_cv2(path: Union[str, Path]) -> np.ndarray:
    """Load image using OpenCV."""
    if not OPENCV_AVAILABLE:
        raise RuntimeError("OpenCV is required for advanced image processing")
    
    try:
        img = cv2.imread(str(path))
        if img is None:
            raise ValueError(f"Could not load image: {path}")
        # Convert BGR to RGB
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        return img
    except Exception as e:
        logger.error("Failed to load image with OpenCV: %s", e)
        raise

def _image_to_base64(image_path: Union[str, Path]) -> str:
    """Convert image to base64 string."""
    try:
        with open(image_path, 'rb') as img_file:
            return base64.b64encode(img_file.read()).decode('utf-8')
    except Exception as e:
        logger.error("Failed to convert image to base64: %s", e)
        raise

# ── OCR Functions ──────────────────────────────────────────────────────────

def _ocr_tesseract(image_path: Path, languages: str = 'eng') -> Dict[str, Any]:
    """Perform OCR using Tesseract."""
    if not TESSERACT_AVAILABLE:
        return {"error": "Tesseract OCR not available"}
    
    try:
        img = _load_image_pil(image_path)
        
        # Extract text
        text = pytesseract.image_to_string(img, lang=languages)
        
        # Get detailed data with bounding boxes
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        
        # Extract words with confidence scores
        words = []
        n_boxes = len(data['text'])
        for i in range(n_boxes):
            if int(data['conf'][i]) > 0:  # Filter out low confidence detections
                words.append({
                    'text': data['text'][i],
                    'confidence': int(data['conf'][i]),
                    'bbox': {
                        'x': data['left'][i],
                        'y': data['top'][i], 
                        'width': data['width'][i],
                        'height': data['height'][i]
                    }
                })
        
        return {
            'method': 'tesseract',
            'text': text.strip(),
            'words': words,
            'word_count': len([w for w in words if w['text'].strip()]),
            'languages': languages
        }
        
    except Exception as e:
        logger.error("Tesseract OCR failed: %s", e)
        return {"error": f"Tesseract OCR failed: {e}"}

def _ocr_easyocr(image_path: Path, languages: List[str] = None) -> Dict[str, Any]:
    """Perform OCR using EasyOCR."""
    if languages is None:
        languages = ['en']
    
    try:
        reader = _get_easyocr()
        if reader is None:
            return {"error": "EasyOCR not available"}
        if languages != ['en']:
            import easyocr
            reader = easyocr.Reader(languages)
        results = reader.readtext(str(image_path))
        
        text_lines = []
        words = []
        
        for (bbox, text, confidence) in results:
            text_lines.append(text)
            words.append({
                'text': text,
                'confidence': int(confidence * 100),
                'bbox': {
                    'x': int(min(point[0] for point in bbox)),
                    'y': int(min(point[1] for point in bbox)),
                    'width': int(max(point[0] for point in bbox) - min(point[0] for point in bbox)),
                    'height': int(max(point[1] for point in bbox) - min(point[1] for point in bbox))
                }
            })
        
        return {
            'method': 'easyocr',
            'text': '\n'.join(text_lines),
            'words': words,
            'word_count': len(words),
            'languages': languages
        }
        
    except Exception as e:
        logger.error("EasyOCR failed: %s", e)
        return {"error": f"EasyOCR failed: {e}"}

# ── Object Detection Functions ─────────────────────────────────────────────

def _detect_objects_basic(image_path: Path) -> Dict[str, Any]:
    """Basic object detection using OpenCV built-in methods."""
    if not OPENCV_AVAILABLE:
        return {"error": "OpenCV not available for object detection"}
    
    try:
        img = _load_image_cv2(image_path)
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        
        # Face detection using Haar cascades
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        faces = face_cascade.detectMultiScale(gray, 1.1, 4)
        
        # Edge detection
        edges = cv2.Canny(gray, 50, 150)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Shape detection
        shapes = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area > 500:  # Filter small shapes
                approx = cv2.approxPolyDP(contour, 0.02 * cv2.arcLength(contour, True), True)
                x, y, w, h = cv2.boundingRect(contour)
                shapes.append({
                    'type': 'polygon',
                    'vertices': len(approx),
                    'area': int(area),
                    'bbox': {'x': int(x), 'y': int(y), 'width': int(w), 'height': int(h)}
                })
        
        return {
            'method': 'opencv_basic',
            'faces': [{'x': int(x), 'y': int(y), 'width': int(w), 'height': int(h)} 
                     for (x, y, w, h) in faces],
            'face_count': len(faces),
            'shapes': shapes,
            'shape_count': len(shapes),
            'total_contours': len(contours)
        }
        
    except Exception as e:
        logger.error("Basic object detection failed: %s", e)
        return {"error": f"Object detection failed: {e}"}

# ── Image Analysis Functions ─────────────────────────────────────────────────

def _analyze_image_properties(image_path: Path) -> Dict[str, Any]:
    """Analyze basic image properties."""
    if not PIL_AVAILABLE:
        return {"error": "PIL not available for image analysis"}
    
    try:
        img = _load_image_pil(image_path)
        
        # Basic properties
        width, height = img.size
        mode = img.mode
        format_name = img.format or 'Unknown'
        
        # File size
        file_size = image_path.stat().st_size
        
        # Color analysis
        colors = img.getcolors(maxcolors=256*256*256)
        dominant_colors = []
        if colors:
            # Sort by frequency and get top colors
            colors.sort(reverse=True)
            for count, color in colors[:5]:
                if isinstance(color, tuple) and len(color) >= 3:
                    dominant_colors.append({
                        'color': color[:3],  # RGB values
                        'count': count,
                        'percentage': round(count / (width * height) * 100, 2)
                    })
        
        # Brightness analysis
        grayscale = img.convert('L')
        pixel_values = list(grayscale.getdata())
        avg_brightness = sum(pixel_values) / len(pixel_values)
        
        return {
            'dimensions': {'width': width, 'height': height},
            'mode': mode,
            'format': format_name,
            'file_size_bytes': file_size,
            'file_size_mb': round(file_size / (1024 * 1024), 2),
            'aspect_ratio': round(width / height, 2),
            'total_pixels': width * height,
            'average_brightness': round(avg_brightness, 2),
            'dominant_colors': dominant_colors
        }
        
    except Exception as e:
        logger.error("Image analysis failed: %s", e)
        return {"error": f"Image analysis failed: {e}"}

# ── Tool Handler Functions ──────────────────────────────────────────────────

def analyze_image(path: str, 
                 ocr: bool = True, 
                 ocr_method: str = 'auto',
                 ocr_languages: str = 'eng',
                 detect_objects: bool = False,
                 analyze_properties: bool = True) -> str:
    """
    Comprehensive image analysis with OCR, object detection, and visual understanding.
    
    Args:
        path: Path to the image file
        ocr: Enable text extraction (OCR) 
        ocr_method: OCR method ('tesseract', 'easyocr', 'auto')
        ocr_languages: Languages for OCR (e.g., 'eng', 'eng+fra')
        detect_objects: Enable object detection
        analyze_properties: Analyze image properties (dimensions, colors, etc.)
    """
    try:
        # Sanitize and validate inputs
        path = sanitize_user_input(path, max_length=500)
        ocr_method = sanitize_user_input(ocr_method, max_length=20)
        ocr_languages = sanitize_user_input(ocr_languages, max_length=100)
        
        # Validate image path
        image_path = _validate_image_path(path)
        
        results = {
            'image_path': str(image_path),
            'analysis_timestamp': None,  # Would add timestamp in real implementation
        }
        
        # Image properties analysis
        if analyze_properties:
            logger.info("Analyzing image properties for: %s", image_path)
            results['properties'] = _analyze_image_properties(image_path)
        
        # OCR analysis
        if ocr:
            logger.info("Performing OCR analysis with method: %s", ocr_method)
            
            if ocr_method == 'tesseract' or (ocr_method == 'auto' and TESSERACT_AVAILABLE):
                results['ocr'] = _ocr_tesseract(image_path, ocr_languages)
            elif ocr_method == 'easyocr' or (ocr_method == 'auto' and EASYOCR_AVAILABLE):
                lang_list = ocr_languages.replace('+', ',').split(',')
                results['ocr'] = _ocr_easyocr(image_path, lang_list)
            else:
                results['ocr'] = {"error": "No OCR engine available"}
        
        # Object detection
        if detect_objects:
            logger.info("Performing object detection for: %s", image_path)
            results['objects'] = _detect_objects_basic(image_path)
        
        # Generate summary
        summary_parts = []
        if 'properties' in results and 'error' not in results['properties']:
            props = results['properties']
            summary_parts.append(f"Image: {props['dimensions']['width']}x{props['dimensions']['height']} pixels, {props['format']}")
        
        if 'ocr' in results and 'error' not in results['ocr']:
            word_count = results['ocr'].get('word_count', 0)
            if word_count > 0:
                summary_parts.append(f"Text detected: {word_count} words")
            else:
                summary_parts.append("No text detected")
        
        if 'objects' in results and 'error' not in results['objects']:
            face_count = results['objects'].get('face_count', 0)
            shape_count = results['objects'].get('shape_count', 0)
            if face_count > 0:
                summary_parts.append(f"Faces detected: {face_count}")
            if shape_count > 0:
                summary_parts.append(f"Shapes detected: {shape_count}")
        
        results['summary'] = "; ".join(summary_parts) if summary_parts else "Analysis completed"
        
        # Format output
        output_lines = [f"🖼️  Image Analysis Results for: {image_path.name}"]
        output_lines.append("=" * 60)
        
        if 'properties' in results:
            props = results['properties']
            if 'error' not in props:
                output_lines.append(f"📐 Dimensions: {props['dimensions']['width']} x {props['dimensions']['height']}")
                output_lines.append(f"📁 Format: {props['format']} ({props['file_size_mb']} MB)")
                output_lines.append(f"🌈 Colors: {len(props.get('dominant_colors', []))} dominant colors")
                output_lines.append(f"💡 Brightness: {props['average_brightness']}/255")
            else:
                output_lines.append(f"❌ Properties analysis failed: {props['error']}")
        
        if 'ocr' in results:
            ocr_result = results['ocr']
            if 'error' not in ocr_result:
                output_lines.append(f"\n📝 OCR Results ({ocr_result.get('method', 'unknown')}):")
                if ocr_result.get('text', '').strip():
                    output_lines.append(f"Text found: {ocr_result['word_count']} words")
                    output_lines.append(f"Content preview: {ocr_result['text'][:200]}...")
                else:
                    output_lines.append("No text detected in image")
            else:
                output_lines.append(f"❌ OCR failed: {ocr_result['error']}")
        
        if 'objects' in results:
            obj_result = results['objects']
            if 'error' not in obj_result:
                output_lines.append(f"\n🎯 Object Detection ({obj_result.get('method', 'unknown')}):")
                output_lines.append(f"Faces detected: {obj_result.get('face_count', 0)}")
                output_lines.append(f"Shapes detected: {obj_result.get('shape_count', 0)}")
            else:
                output_lines.append(f"❌ Object detection failed: {obj_result['error']}")
        
        output_lines.append(f"\n✅ {results['summary']}")
        
        return "\n".join(output_lines)
        
    except Exception as e:
        logger.error("Image analysis failed: %s", e)
        return f"❌ Image analysis failed: {e}"

def extract_text(path: str, method: str = 'auto', languages: str = 'eng') -> str:
    """
    Extract text from an image using OCR.
    
    Args:
        path: Path to the image file
        method: OCR method ('tesseract', 'easyocr', 'auto')  
        languages: Languages for OCR (e.g., 'eng', 'eng+fra')
    """
    try:
        # Sanitize inputs
        path = sanitize_user_input(path, max_length=500)
        method = sanitize_user_input(method, max_length=20)
        languages = sanitize_user_input(languages, max_length=100)
        
        # Validate image path
        image_path = _validate_image_path(path)
        
        # Perform OCR
        if method == 'tesseract' or (method == 'auto' and TESSERACT_AVAILABLE):
            result = _ocr_tesseract(image_path, languages)
        elif method == 'easyocr' or (method == 'auto' and EASYOCR_AVAILABLE):
            lang_list = languages.replace('+', ',').split(',')
            result = _ocr_easyocr(image_path, lang_list)
        else:
            return "❌ No OCR engine available. Install pytesseract or easyocr."
        
        if 'error' in result:
            return f"❌ OCR failed: {result['error']}"
        
        extracted_text = result.get('text', '').strip()
        word_count = result.get('word_count', 0)
        
        if extracted_text:
            return f"📝 Extracted {word_count} words:\n\n{extracted_text}"
        else:
            return "📝 No text detected in the image."
            
    except Exception as e:
        logger.error("Text extraction failed: %s", e)
        return f"❌ Text extraction failed: {e}"

def detect_objects_in_image(path: str) -> str:
    """
    Detect objects, faces, and shapes in an image.
    
    Args:
        path: Path to the image file
    """
    try:
        # Sanitize input
        path = sanitize_user_input(path, max_length=500)
        
        # Validate image path
        image_path = _validate_image_path(path)
        
        # Perform object detection
        result = _detect_objects_basic(image_path)
        
        if 'error' in result:
            return f"❌ Object detection failed: {result['error']}"
        
        output_lines = [f"🎯 Object Detection Results for: {image_path.name}"]
        output_lines.append("=" * 50)
        
        face_count = result.get('face_count', 0)
        shape_count = result.get('shape_count', 0)
        
        output_lines.append(f"👥 Faces detected: {face_count}")
        if face_count > 0:
            for i, face in enumerate(result.get('faces', []), 1):
                output_lines.append(f"   Face {i}: position ({face['x']}, {face['y']}) size {face['width']}x{face['height']}")
        
        output_lines.append(f"🔷 Shapes detected: {shape_count}")
        if shape_count > 0:
            for i, shape in enumerate(result.get('shapes', [])[:5], 1):  # Limit to 5 shapes
                output_lines.append(f"   Shape {i}: {shape['vertices']} vertices, area {shape['area']}")
        
        output_lines.append(f"\n✅ Analysis complete: {face_count} faces, {shape_count} shapes detected")
        
        return "\n".join(output_lines)
        
    except Exception as e:
        logger.error("Object detection failed: %s", e)
        return f"❌ Object detection failed: {e}"

# ── Tool Registration ────────────────────────────────────────────────────────

# Register the image analysis tools
registry.register(
    name="AnalyzeImage",
    description="Comprehensive image analysis with OCR, object detection, and visual understanding",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the image file"},
            "ocr": {"type": "boolean", "default": True, "description": "Enable text extraction (OCR)"},
            "ocr_method": {"type": "string", "default": "auto", "description": "OCR method: 'tesseract', 'easyocr', or 'auto'"},
            "ocr_languages": {"type": "string", "default": "eng", "description": "OCR languages (e.g., 'eng', 'eng+fra')"},
            "detect_objects": {"type": "boolean", "default": False, "description": "Enable object detection"},
            "analyze_properties": {"type": "boolean", "default": True, "description": "Analyze image properties"}
        },
        "required": ["path"]
    },
    handler=analyze_image,
    category="image"
)

registry.register(
    name="ExtractText",
    description="Extract text from an image using OCR",
    parameters={
        "type": "object", 
        "properties": {
            "path": {"type": "string", "description": "Path to the image file"},
            "method": {"type": "string", "default": "auto", "description": "OCR method: 'tesseract', 'easyocr', or 'auto'"},
            "languages": {"type": "string", "default": "eng", "description": "OCR languages (e.g., 'eng', 'eng+fra')"}
        },
        "required": ["path"]
    },
    handler=extract_text,
    category="image"
)

registry.register(
    name="DetectObjects",
    description="Detect objects, faces, and shapes in an image",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the image file"}
        },
        "required": ["path"]
    },
    handler=detect_objects_in_image,
    category="image"
)

logger.info("Image analysis tools registered: AnalyzeImage, ExtractText, DetectObjects")
