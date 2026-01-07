/**
 * Canvas Engine - TypeScript port (permissive types)
 * Kept lightweight: most Konva objects typed as `any` to allow incremental migration.
 */

import Konva from 'konva'

export class CanvasEngine {
  stage: Konva.Stage
  imageLayer: Konva.Layer
  cropLayer: Konva.Layer
  transformer: Konva.Transformer
  transformerAdded: boolean
  activeTool: string | null
  currentImage: Konva.Image | null
  originalDimensions: { width: number; height: number }
  displayScale: number
  imageScale: number
  combinedScale: number
  minZoomScale: number
  listeners: Map<string, Array<(...args: unknown[]) => void>>
  isPanning: boolean
  lastPosX: number
  lastPosY: number

  constructor(canvasElement: HTMLCanvasElement, options: Record<string, unknown> = {}) {
    const wrapper = canvasElement.parentElement
    if (!wrapper) throw new Error('Canvas element must be attached to a parent element')

    this.stage = new Konva.Stage({
      container: wrapper as HTMLDivElement,
      width: (canvasElement as HTMLCanvasElement).width || 800,
      height: (canvasElement as HTMLCanvasElement).height || 600
    })

    canvasElement.style.display = 'none'

    this.imageLayer = new Konva.Layer()
    this.cropLayer = new Konva.Layer()

    this.stage.add(this.imageLayer)
    this.stage.add(this.cropLayer)

    this.transformer = new Konva.Transformer({
      borderStroke: '#3b82f6',
      borderStrokeWidth: 1,
      anchorFill: '#3b82f6',
      anchorStroke: '#fff',
      anchorStrokeWidth: 1,
      anchorSize: 8,
      anchorCornerRadius: 4,
      borderDash: [5, 5],
      keepRatio: false,
      enabledAnchors: [
        'top-left',
        'top-center',
        'top-right',
        'middle-right',
        'middle-left',
        'bottom-left',
        'bottom-center',
        'bottom-right'
      ],
      rotateEnabled: true,
      flipEnabled: false
    })

    this.transformerAdded = false

    this.activeTool = null
    this.currentImage = null
    this.originalDimensions = { width: 0, height: 0 }
    this.displayScale = 1
    this.imageScale = 1
    this.combinedScale = 1
    this.minZoomScale = 1
    this.listeners = new Map()
    this.isPanning = false
    this.lastPosX = 0
    this.lastPosY = 0

    this._setupEvents()
    this._setupZoomPan()
  }

  async loadImage(url: string, originalWidth: number | null = null) {
    return new Promise<void>((resolve, reject) => {
      const imageObj = new Image()
      imageObj.crossOrigin = 'anonymous'

      imageObj.onload = () => {
        this.imageLayer.destroyChildren()

        const crops = this.cropLayer.find?.('.cropBox') ?? []
        crops.forEach((crop: Konva.Node) => crop.destroy())

        this.transformer.nodes([])

        if (originalWidth) {
          this.originalDimensions = {
            width: originalWidth,
            height: imageObj.height * (originalWidth / imageObj.width)
          }
        } else {
          this.originalDimensions = { width: imageObj.width, height: imageObj.height }
        }

        const imageScale = originalWidth ? imageObj.width / originalWidth : 1

        const container = this.stage.container()
        const containerWidth = container.clientWidth - 40
        const containerHeight = container.clientHeight - 40

        const scaleX = containerWidth / imageObj.width
        const scaleY = containerHeight / imageObj.height
        const displayScale = Math.min(scaleX, scaleY, 1)
        this.displayScale = displayScale
        this.imageScale = imageScale
        this.combinedScale = imageScale * displayScale
        this.minZoomScale = 1

        const canvasWidth = imageObj.width * displayScale
        const canvasHeight = imageObj.height * displayScale

        this.stage.width(canvasWidth)
        this.stage.height(canvasHeight)

        this.currentImage = new Konva.Image({
          image: imageObj,
          x: 0,
          y: 0,
          width: imageObj.width,
          height: imageObj.height,
          scaleX: displayScale,
          scaleY: displayScale,
          draggable: false,
          listening: false,
          offsetX: 0,
          offsetY: 0,
          rotation: 0
        })

        this.imageLayer.add(this.currentImage)
        this.imageLayer.batchDraw()

        this.resetZoom()

        this._emit('imageLoaded', { width: canvasWidth, height: canvasHeight })
        resolve()
      }

      imageObj.onerror = () => {
        reject(new Error('Failed to load image'))
      }

      imageObj.src = url
    })
  }

  activateTool(toolName: string) {
    this.deactivateTool()

    switch (toolName) {
      case 'crop':
        this._activateCropTool()
        break
      case 'select':
        break
      default:
        console.warn(`Unknown tool: ${toolName}`)
    }

    this.activeTool = toolName
    this._emit('toolActivated', { tool: toolName })
  }

  deactivateTool() {
    this.activeTool = null
  }

  addCropBox(options: any = {}) {
    const defaultOptions = { x: 50, y: 50, width: 300, height: 400, autoSelect: true }
    const finalOptions = { ...defaultOptions, ...options }
    const autoSelect = finalOptions.autoSelect
    delete finalOptions.autoSelect

    const rect = new Konva.Rect({
      x: finalOptions.x ?? finalOptions.left ?? 50,
      y: finalOptions.y ?? finalOptions.top ?? 50,
      width: finalOptions.width,
      height: finalOptions.height,
      fill: 'rgba(59, 130, 246, 0.15)',
      stroke: '#3b82f6',
      strokeWidth: 2,
      strokeScaleEnabled: false,
      dash: [8, 8],
      draggable: true,
      name: 'cropBox'
    })

    rect.on('click tap', () => {
      this.transformer.nodes([rect])
      this.transformer.forceUpdate()
      this.cropLayer.batchDraw()
    })

    rect.on('dragend transformend', () => {
      this._emit('modified')
    })

    this.cropLayer.add(rect)

    if (!this.transformerAdded) {
      this.cropLayer.add(this.transformer)
      this.transformerAdded = true
      this.cropLayer.batchDraw()
    }

    if (autoSelect) {
      this.transformer.nodes([rect])
      this.transformer.forceUpdate()
    }

    this.cropLayer.batchDraw()

    this._emit('objectAdded', { type: 'cropBox' })
    return rect
  }

  getCropBoxes() {
    const crops = this.cropLayer.find('.cropBox')
    const displayScale = this.displayScale || 1
    const stageInv = this.stage.getAbsoluteTransform().copy().invert()

    const img = this.currentImage
    if (!img) return []

    const rad = (img.rotation() * Math.PI) / 180

    if (!img) return []

    const rotatedW_UI = (Math.abs(img.width() * Math.cos(rad)) + Math.abs(img.height() * Math.sin(rad))) * displayScale
    const rotatedH_UI = (Math.abs(img.width() * Math.sin(rad)) + Math.abs(img.height() * Math.cos(rad))) * displayScale

    const topLeftX = img.x() - rotatedW_UI / 2
    const topLeftY = img.y() - rotatedH_UI / 2

    console.group('🔍 getCropBoxes Debug')
    console.log('Stage transform (scale/pos):', { scale: this.stage.scaleX(), x: this.stage.x(), y: this.stage.y() })
    console.log('Display scale:', displayScale)
    console.log('Image bounds:', { topLeftX, topLeftY, rotatedW_UI, rotatedH_UI })

    return crops.map((rect: any) => {
      const absTL = rect.getAbsoluteTransform().point({ x: 0, y: 0 })
      const absTR = rect.getAbsoluteTransform().point({ x: rect.width() * rect.scaleX(), y: 0 })
      const absBL = rect.getAbsoluteTransform().point({ x: 0, y: rect.height() * rect.scaleY() })

      const tl = stageInv.point(absTL)
      const tr = stageInv.point(absTR)
      const bl = stageInv.point(absBL)

      const w_display = Math.hypot(tr.x - tl.x, tr.y - tl.y)
      const h_display = Math.hypot(bl.x - tl.x, bl.y - tl.y)

      const x_display = tl.x
      const y_display = tl.y

      const x = (x_display - topLeftX) / displayScale
      const y = (y_display - topLeftY) / displayScale
      const w = w_display / displayScale
      const h = h_display / displayScale

      const result = { x: Math.round(x), y: Math.round(y), w: Math.round(w), h: Math.round(h) }

      console.log('Rect abs TL:', absTL, 'unzoomed TL:', tl)
      console.log('Rect size (display):', { w_display, h_display })
      console.log('Final result:', result)
      console.groupEnd()

      return result
    })
  }

  getCropBoxesForOriginal() {
    const crops = this.cropLayer.find('.cropBox')
    if (crops.length === 0) return []

    const imgNode = this.currentImage
    if (!imgNode) return []

    const rotation = imgNode.rotation()
    const rad = (rotation * Math.PI) / 180

    const combinedScale = this.combinedScale || this.displayScale * this.imageScale

    const imgW_canvas = imgNode.width() * imgNode.scaleX()
    const imgH_canvas = imgNode.height() * imgNode.scaleY()

    console.group('💾 Saving Bbox to Original Coordinates')
    console.log('Rotation:', rotation, 'degrees')
    console.log('Combined scale:', combinedScale)
    console.log('Image on canvas (WxH):', imgW_canvas, 'x', imgH_canvas)

    return crops.map((rect: any) => {
      const x_display = rect.x()
      const y_display = rect.y()
      const w_display = rect.width() * rect.scaleX()
      const h_display = rect.height() * rect.scaleY()

      console.log('Bbox on canvas (display):', { x: x_display, y: y_display, w: w_display, h: h_display })

      const result = {
        x: Math.round(x_display / combinedScale),
        y: Math.round(y_display / combinedScale),
        w: Math.round(w_display / combinedScale),
        h: Math.round(h_display / combinedScale)
      }

      console.log('Bbox in original coordinates:', result)
      console.groupEnd()

      return result
    })
  }

  loadCropBoxes(boxes: Array<any>) {
    boxes.forEach(box => {
      const scale = this.combinedScale || this.displayScale || 1

      console.group('📦 Loading Bbox')
      console.log('Original bbox (metadata):', box)
      console.log('Image scale (original→loaded):', this.imageScale)
      console.log('Display scale (loaded→canvas):', this.displayScale)
      console.log('Combined scale:', scale)
      console.log('Original dimensions:', this.originalDimensions)
      const loadedImage = this.currentImage?.image()
      const loadedW = (loadedImage as any)?.width ?? null
      const loadedH = (loadedImage as any)?.height ?? null
      console.log('Loaded image actual size:', loadedW, 'x', loadedH)
      console.log('Stage size:', this.stage.width(), 'x', this.stage.height())
      console.log('Expected canvas bbox if metadata is correct:', { x: box.x * scale, y: box.y * scale, w: box.w * scale, h: box.h * scale })
      console.log('Bbox % of original image:', {
        x_pct: (box.x / this.originalDimensions.width * 100).toFixed(1) + '%',
        y_pct: (box.y / this.originalDimensions.height * 100).toFixed(1) + '%',
        w_pct: (box.w / this.originalDimensions.width * 100).toFixed(1) + '%',
        h_pct: (box.h / this.originalDimensions.height * 100).toFixed(1) + '%'
      })

      const img = this.currentImage
      if (img) {
        console.log('🖼️ Image position on stage:', {
          x: img.x(),
          y: img.y(),
          width: img.width(),
          height: img.height(),
          scaleX: img.scaleX(),
          scaleY: img.scaleY(),
          offsetX: img.offsetX(),
          offsetY: img.offsetY(),
          rotation: img.rotation()
        })
      } else {
        console.log('🖼️ No current image on stage')
      }
      console.log('📐 Stage position:', { x: this.stage.x(), y: this.stage.y(), width: this.stage.width(), height: this.stage.height() })

      const scaledBox = { x: box.x * scale, y: box.y * scale, width: box.w * scale, height: box.h * scale, autoSelect: false }

      console.log('Scaled bbox (canvas coords):', scaledBox)
      console.groupEnd()

      this.addCropBox(scaledBox)
    })
  }

  zoomIn() {
    const oldScale = this.stage.scaleX()
    const newScale = Math.min(oldScale * 1.1, 5)
    const center = { x: this.stage.width() / 2, y: this.stage.height() / 2 }
    this._zoomToPoint(center, newScale)
    this._emit('zoomChanged', { zoom: newScale })
  }

  zoomOut() {
    const oldScale = this.stage.scaleX()
    const newScale = Math.max(oldScale * 0.9, this.minZoomScale)
    const center = { x: this.stage.width() / 2, y: this.stage.height() / 2 }
    this._zoomToPoint(center, newScale)
    this._emit('zoomChanged', { zoom: newScale })
  }

  resetZoom() {
    this.stage.scale({ x: 1, y: 1 })
    this.centerView()
    this._emit('zoomChanged', { zoom: 1 })
  }

  centerView() {
    if (!this.currentImage) return

    const stageWidth = this.stage.width()
    const stageHeight = this.stage.height()
    const scale = this.stage.scaleX()

    const imageWidth = this.currentImage.width() * this.currentImage.scaleX() * scale
    const imageHeight = this.currentImage.height() * this.currentImage.scaleY() * scale

    const x = (stageWidth - imageWidth) / 2
    const y = (stageHeight - imageHeight) / 2

    this.stage.position({ x: imageWidth > stageWidth ? 0 : Math.max(0, x), y: imageHeight > stageHeight ? 0 : Math.max(0, y) })
    this.stage.batchDraw()
  }

  fitToCanvas() {
    this.resetZoom()
  }

  resetView() {
    this.resetZoom()
  }

  getZoom() {
    return this.stage.scaleX()
  }

  deleteSelected() {
    const selected = this.transformer.nodes()
    if (selected.length > 0) {
      selected.forEach((node: Konva.Node) => node.destroy())
      this.transformer.nodes([])
      this.cropLayer.batchDraw()
      this._emit('objectDeleted')
    }
  }

  clear() {
    const crops = this.cropLayer.find('.cropBox')
    crops.forEach((crop: Konva.Node) => crop.destroy())
    this.transformer.nodes([])
    this.cropLayer.batchDraw()
    this._emit('cleared')
  }

  getScaleFactor() {
    if (!this.currentImage) return 1
    return this.originalDimensions.width / this.stage.width()
  }

  toDataURL(options: { format?: string; quality?: number } = {}) {
    const { format = 'png', quality = 1 } = options

    const currentScale = this.stage.scaleX()
    const currentPos = this.stage.position()

    this.stage.scale({ x: 1, y: 1 })
    this.stage.position({ x: 0, y: 0 })

    const dataUrl = this.imageLayer.toDataURL({ pixelRatio: 1, mimeType: `image/${format}`, quality })

    this.stage.scale({ x: currentScale, y: currentScale })
    this.stage.position(currentPos)

    return dataUrl
  }

  async getTransformedFullCanvas() {
    if (!this.currentImage) return null
    const originalAttrs = {
      x: this.currentImage.x(),
      y: this.currentImage.y(),
      scaleX: this.currentImage.scaleX(),
      scaleY: this.currentImage.scaleY(),
      rotation: this.currentImage.rotation(),
      offsetX: this.currentImage.offsetX(),
      offsetY: this.currentImage.offsetY()
    }

    const img = this.currentImage?.image()
    const rotation = this.currentImage ? this.currentImage.rotation() : 0
    const rad = (rotation * Math.PI) / 180

    const imgEl = this._getImageElement()
    if (!imgEl) return null
    const imgWidthSrc = imgEl.width
    const imgHeightSrc = imgEl.height

    const rotatedW = Math.round(Math.abs(imgWidthSrc * Math.cos(rad)) + Math.abs(imgHeightSrc * Math.sin(rad)))
    const rotatedH = Math.round(Math.abs(imgWidthSrc * Math.sin(rad)) + Math.abs(imgHeightSrc * Math.cos(rad)))

    // Preserve stage transform and temporarily reset it so exported canvas is independent
    const stageScale = this.stage.scaleX()
    const stagePos = this.stage.position()

    // Render image at scale 1 with rotation applied via image attrs
    this.stage.scale({ x: 1, y: 1 })
    this.stage.position({ x: 0, y: 0 })

    this.currentImage.setAttrs({ scaleX: 1, scaleY: 1, x: rotatedW / 2, y: rotatedH / 2, offsetX: imgWidthSrc / 2, offsetY: imgHeightSrc / 2, rotation })

    const canvas = this.imageLayer.toCanvas({ x: 0, y: 0, width: rotatedW, height: rotatedH, pixelRatio: 1 })

    // Restore original attributes and stage transform
    this.currentImage.setAttrs(originalAttrs)
    this.stage.scale({ x: stageScale, y: stageScale })
    this.stage.position(stagePos)
    this.imageLayer.batchDraw()

    return canvas
  }

  async exportCropBoxFromOriginal(options: { format?: string; quality?: number } = {}) {
    const { format = 'png', quality = 1 } = options

    const originalCrops = this.getCropBoxes()
    if (originalCrops.length === 0) return null
    const crop = originalCrops[0]

    const fullCanvas = await this.getTransformedFullCanvas()
    if (!fullCanvas) return null

    const cropCanvas = document.createElement('canvas')
    cropCanvas.width = crop.w
    cropCanvas.height = crop.h
    const ctx = cropCanvas.getContext('2d')
    if (ctx) {
      ctx.drawImage(fullCanvas, crop.x, crop.y, crop.w, crop.h, 0, 0, crop.w, crop.h)
    } else {
      console.warn('Failed to get 2D context for crop canvas')
      return null
    }

    return cropCanvas.toDataURL(`image/${format}`, quality)
  }

  getImageUrl() {
    if (!this.currentImage || !this.currentImage.image()) return null
    const el = this._getImageElement()
    return el?.src ?? null
  }

  private _getImageElement(): HTMLImageElement | null {
    const img = this.currentImage?.image()
    if (!img) return null
    // If the underlying image is an HTMLImageElement, return it
    if ((img as HTMLImageElement).src !== undefined) return img as HTMLImageElement
    return null
  }

  getRotation() {
    return this.currentImage ? this.currentImage.rotation() : 0
  }

  getFilters() {
    if (!this.currentImage) return { brightness: 0, contrast: 0 }

    return { brightness: this.currentImage.brightness() || 0, contrast: (this.currentImage.contrast() || 0) / 100 }
  }

  applyBrightnessContrast() {
    if (this.imageLayer) {
      this.imageLayer.batchDraw()
    }
  }

  fitToContainer(maxWidth = 1200, maxHeight = 800) {
    if (!this.currentImage) return

    const scale = Math.min(maxWidth / this.currentImage.width(), maxHeight / this.currentImage.height(), 1)

    this.stage.width(this.currentImage.width() * scale)
    this.stage.height(this.currentImage.height() * scale)
    this.stage.batchDraw()
  }

  on(event: string, callback: (...args: any[]) => void) {
    if (!this.listeners.has(event)) this.listeners.set(event, [])
    this.listeners.get(event)!.push(callback)
  }

  off(event: string, callback: (...args: any[]) => void) {
    if (this.listeners.has(event)) {
      const callbacks = this.listeners.get(event)!
      const index = callbacks.indexOf(callback)
      if (index > -1) callbacks.splice(index, 1)
    }
  }

  destroy() {
    this.stage.destroy()
    this.listeners.clear()
  }

  applyRotation(angle: number) {
    if (!this.currentImage) return

    const centerX = (this.currentImage.width() * this.currentImage.scaleX()) / 2
    const centerY = (this.currentImage.height() * this.currentImage.scaleY()) / 2

    this.currentImage.rotation(angle)
    this.currentImage.offsetX(this.currentImage.width() / 2)
    this.currentImage.offsetY(this.currentImage.height() / 2)
    this.currentImage.x(centerX)
    this.currentImage.y(centerY)

    this.imageLayer.batchDraw()
  }

  applyFilters(options: { brightness?: number; contrast?: number } = {}) {
    if (!this.currentImage) return

    const { brightness = 0, contrast = 0 } = options

    this.currentImage.filters([])

    if (Math.abs(brightness) > 0.01) this.currentImage.brightness(brightness)
    if (Math.abs(contrast) > 0.01) this.currentImage.contrast(contrast * 100)

    this.currentImage.cache()
    this.imageLayer.batchDraw()
  }

  _activateCropTool() {
    this.addCropBox({ x: this.stage.width() / 4, y: this.stage.height() / 4, width: this.stage.width() / 2, height: this.stage.height() / 2 })
  }

  _setupEvents() {
    this.stage.on('click tap', (e: any) => {
      if (e.target === this.stage || e.target === this.imageLayer || e.target === this.currentImage) {
        this.transformer.nodes([])
        this.cropLayer.batchDraw()
      }
    })

    this.stage.on('mousedown touchstart', (e: any) => {
      if (e.target.hasName && e.target.hasName('cropBox')) {
        this.transformer.nodes([e.target])
        this.transformer.forceUpdate()
        this.cropLayer.batchDraw()
      }
    })

    document.addEventListener('keydown', (e: KeyboardEvent) => {
      if (e.key === 'Delete' || e.key === 'Backspace') {
        const target = e.target as HTMLElement
        if (target.tagName !== 'INPUT' && target.tagName !== 'TEXTAREA') {
          this.deleteSelected()
        }
      }
    })
  }

  _setupZoomPan() {
    this.stage.on('wheel', (e: any) => {
      e.evt.preventDefault()

      if (Math.abs(e.evt.deltaX) > Math.abs(e.evt.deltaY)) {
        const newPos = { x: this.stage.x() - e.evt.deltaX, y: this.stage.y() - e.evt.deltaY }
        this.stage.position(this._constrainPan(newPos))
        this.stage.batchDraw()
        return
      }

      const oldScale = this.stage.scaleX()
      const pointer = this.stage.getPointerPosition()
      if (!pointer) return

      const scaleBy = 1.05
      const direction = e.evt.deltaY > 0 ? -1 : 1

      let newScale = direction > 0 ? oldScale * scaleBy : oldScale / scaleBy
      newScale = Math.max(this.minZoomScale, Math.min(5, newScale))

      this._zoomToPoint(pointer, newScale)
      this._emit('zoomChanged', { zoom: newScale })
    })

    this.stage.on('mousedown', (e: any) => {
      const evt = e.evt
      if (evt.button === 0 && (e.target === this.stage || e.target === this.imageLayer || e.target === this.currentImage)) {
        this.isPanning = true
        this.stage.container().style.cursor = 'grab'
        this.lastPosX = evt.clientX
        this.lastPosY = evt.clientY
        evt.preventDefault()
      }
    })

    this.stage.on('mousemove', (e: any) => {
      if (!this.isPanning) return

      const evt = e.evt
      const dx = evt.clientX - this.lastPosX
      const dy = evt.clientY - this.lastPosY

      const newPos = { x: this.stage.x() + dx, y: this.stage.y() + dy }

      this.stage.position(this._constrainPan(newPos))
      this.stage.batchDraw()

      this.lastPosX = evt.clientX
      this.lastPosY = evt.clientY
      this.stage.container().style.cursor = 'grabbing'
    })

    this.stage.on('mouseup', () => {
      if (this.isPanning) {
        this.isPanning = false
        this.stage.container().style.cursor = 'default'
      }
    })

    this.stage.on('mouseleave', () => {
      if (this.isPanning) {
        this.isPanning = false
        this.stage.container().style.cursor = 'default'
      }
    })
  }

  _zoomToPoint(point: { x: number; y: number }, newScale: number) {
    const oldScale = this.stage.scaleX()
    const mousePointTo = { x: (point.x - this.stage.x()) / oldScale, y: (point.y - this.stage.y()) / oldScale }

    this.stage.scale({ x: newScale, y: newScale })

    const newPos = { x: point.x - mousePointTo.x * newScale, y: point.y - mousePointTo.y * newScale }

    this.stage.position(this._constrainPan(newPos))
    this.stage.batchDraw()
  }

  _constrainPan(pos: { x: number; y: number }) {
    if (!this.currentImage) return pos

    const scale = this.stage.scaleX()
    const stageWidth = this.stage.width()
    const stageHeight = this.stage.height()

    const imageWidth = this.currentImage.width() * this.currentImage.scaleX() * scale
    const imageHeight = this.currentImage.height() * this.currentImage.scaleY() * scale

    const marginX = imageWidth * 0.2
    const marginY = imageHeight * 0.2

    const minX = stageWidth - imageWidth - marginX
    const maxX = marginX

    const minY = stageHeight - imageHeight - marginY
    const maxY = marginY

    return { x: Math.max(minX, Math.min(maxX, pos.x)), y: Math.max(minY, Math.min(maxY, pos.y)) }
  }

  _emit(event: string, data: any = {}) {
    if (this.listeners.has(event)) {
      this.listeners.get(event)!.forEach(cb => cb(data))
    }
  }
}
