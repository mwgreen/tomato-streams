// Draws the tvOS app icon (layered), App Store icon and Top Shelf images into
// StreamingFinder/Assets.xcassets. Run from tvos/:  swift icon/make_icon.swift
// Tweak the colours / proportions below and re-run; the PNGs are regenerated.
import AppKit
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers

// MARK: palette (matches web/icon.png: red tomato, green top, near-black background)

func rgb(_ hex: UInt32, _ a: CGFloat = 1) -> CGColor {
    CGColor(red: CGFloat((hex >> 16) & 0xff) / 255, green: CGFloat((hex >> 8) & 0xff) / 255,
            blue: CGFloat(hex & 0xff) / 255, alpha: a)
}
let bgTop = rgb(0x1b2230), bgBottom = rgb(0x0b0e14)
let glow = rgb(0xff4a2a, 0.30)
let redLight = rgb(0xff5e45), redMid = rgb(0xe42a17), redDark = rgb(0x9a0f08)
let leafLight = rgb(0x4cc24a), leafDark = rgb(0x1c7a24)

// MARK: drawing helpers

func makeContext(_ w: Int, _ h: Int) -> CGContext {
    let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: 0,
                        space: CGColorSpace(name: CGColorSpace.sRGB)!,
                        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
    ctx.interpolationQuality = .high
    ctx.setShouldAntialias(true)
    return ctx
}

func save(_ ctx: CGContext, _ path: String, opaque: Bool) {
    var image = ctx.makeImage()!
    if opaque {  // the back layer / top shelf must not carry alpha
        let flat = CGContext(data: nil, width: image.width, height: image.height, bitsPerComponent: 8, bytesPerRow: 0,
                             space: CGColorSpace(name: CGColorSpace.sRGB)!,
                             bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)!
        flat.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))
        image = flat.makeImage()!
    }
    let url = URL(fileURLWithPath: path)
    try? FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
    let dest = CGImageDestinationCreateWithURL(url as CFURL, UTType.png.identifier as CFString, 1, nil)!
    CGImageDestinationAddImage(dest, image, nil)
    CGImageDestinationFinalize(dest)
}

func background(_ ctx: CGContext, _ size: CGSize, glowAt center: CGPoint, glowRadius: CGFloat) {
    let space = CGColorSpace(name: CGColorSpace.sRGB)!
    let g = CGGradient(colorsSpace: space, colors: [bgTop, bgBottom] as CFArray, locations: [0, 1])!
    ctx.drawLinearGradient(g, start: CGPoint(x: 0, y: size.height), end: CGPoint(x: 0, y: 0), options: [])
    let r = CGGradient(colorsSpace: space, colors: [glow, rgb(0xff4a2a, 0)] as CFArray, locations: [0, 1])!
    ctx.drawRadialGradient(r, startCenter: center, startRadius: 0, endCenter: center, endRadius: glowRadius, options: [])
}

/// Tomato body + drop shadow. `c` is the body centre, `r` its radius.
func tomatoBody(_ ctx: CGContext, c: CGPoint, r: CGFloat) {
    let body = CGRect(x: c.x - r * 1.07, y: c.y - r * 0.95, width: r * 2.14, height: r * 1.9)
    let space = CGColorSpace(name: CGColorSpace.sRGB)!
    // shadow
    ctx.saveGState()
    ctx.setShadow(offset: CGSize(width: 0, height: -r * 0.10), blur: r * 0.35, color: rgb(0x000000, 0.55))
    ctx.setFillColor(redDark)
    ctx.fillEllipse(in: body)
    ctx.restoreGState()
    // body gradient, lit from the upper left
    ctx.saveGState()
    ctx.addEllipse(in: body)
    ctx.clip()
    let g = CGGradient(colorsSpace: space, colors: [redLight, redMid, redDark] as CFArray, locations: [0, 0.55, 1])!
    let light = CGPoint(x: c.x - r * 0.38, y: c.y + r * 0.42)
    ctx.drawRadialGradient(g, startCenter: light, startRadius: 0, endCenter: c, endRadius: r * 1.25,
                           options: [.drawsAfterEndLocation])
    // two soft lobe creases
    ctx.setStrokeColor(rgb(0x8a1008, 0.13))
    ctx.setLineWidth(r * 0.035)
    ctx.setLineCap(.round)
    for dx in [-0.42, 0.42] as [CGFloat] {
        ctx.move(to: CGPoint(x: c.x + r * dx * 0.55, y: c.y + r * 0.78))
        ctx.addQuadCurve(to: CGPoint(x: c.x + r * dx * 1.05, y: c.y - r * 0.55),
                         control: CGPoint(x: c.x + r * dx * 1.25, y: c.y + r * 0.2))
    }
    ctx.strokePath()
    ctx.restoreGState()
}

/// Leaves, stem and gloss: the front layer.
func tomatoTop(_ ctx: CGContext, c: CGPoint, r: CGFloat, gloss: Bool = true) {
    let space = CGColorSpace(name: CGColorSpace.sRGB)!
    let top = CGPoint(x: c.x, y: c.y + r * 0.80)
    // gloss highlight on the body
    if gloss {
        let hl = CGPoint(x: c.x - r * 0.45, y: c.y + r * 0.35)
        let g = CGGradient(colorsSpace: space, colors: [rgb(0xffffff, 0.55), rgb(0xffffff, 0)] as CFArray, locations: [0, 1])!
        ctx.saveGState()
        ctx.translateBy(x: hl.x, y: hl.y)
        ctx.scaleBy(x: 1.0, y: 0.72)
        ctx.drawRadialGradient(g, startCenter: .zero, startRadius: 0, endCenter: .zero, endRadius: r * 0.38, options: [])
        ctx.restoreGState()
    }
    // five sepals radiating from the top, drawn as pointed leaves
    let degrees: [CGFloat] = [180, 252, 324, 36, 108]  // five sepals, 72° apart
    let angles: [CGFloat] = degrees.map { d in d * CGFloat.pi / 180 }
    let lengths: [CGFloat] = [0.46, 0.56, 0.42, 0.42, 0.56]
    ctx.saveGState()
    ctx.setShadow(offset: CGSize(width: 0, height: -r * 0.03), blur: r * 0.08, color: rgb(0x000000, 0.45))
    for (a, len) in zip(angles, lengths) {
        let tip = CGPoint(x: top.x + cos(a) * r * len * 1.15, y: top.y + sin(a) * r * len * 0.55)
        let w = r * 0.26
        let nx = -sin(a) * w, ny = cos(a) * w * 0.6
        let path = CGMutablePath()
        path.move(to: top)
        path.addQuadCurve(to: tip, control: CGPoint(x: (top.x + tip.x) / 2 + nx, y: (top.y + tip.y) / 2 + ny))
        path.addQuadCurve(to: top, control: CGPoint(x: (top.x + tip.x) / 2 - nx, y: (top.y + tip.y) / 2 - ny))
        ctx.addPath(path)
    }
    ctx.addEllipse(in: CGRect(x: top.x - r * 0.15, y: top.y - r * 0.10, width: r * 0.30, height: r * 0.20))
    ctx.setFillColor(leafDark)
    ctx.fillPath()
    ctx.restoreGState()
    // lighter green over the leaves
    ctx.saveGState()
    for (a, len) in zip(angles, lengths) {
        let tip = CGPoint(x: top.x + cos(a) * r * len * 1.05, y: top.y + sin(a) * r * len * 0.48)
        let w = r * 0.15
        let nx = -sin(a) * w, ny = cos(a) * w * 0.6
        let path = CGMutablePath()
        path.move(to: top)
        path.addQuadCurve(to: tip, control: CGPoint(x: (top.x + tip.x) / 2 + nx, y: (top.y + tip.y) / 2 + ny))
        path.addQuadCurve(to: top, control: CGPoint(x: (top.x + tip.x) / 2 - nx, y: (top.y + tip.y) / 2 - ny))
        ctx.addPath(path)
    }
    ctx.setFillColor(leafLight)
    ctx.fillPath()
    ctx.restoreGState()
    // stem
    let stem = CGMutablePath()
    stem.move(to: CGPoint(x: top.x - r * 0.05, y: top.y))
    stem.addQuadCurve(to: CGPoint(x: top.x + r * 0.10, y: top.y + r * 0.30), control: CGPoint(x: top.x - r * 0.04, y: top.y + r * 0.22))
    stem.addLine(to: CGPoint(x: top.x + r * 0.17, y: top.y + r * 0.27))
    stem.addQuadCurve(to: CGPoint(x: top.x + r * 0.06, y: top.y), control: CGPoint(x: top.x + r * 0.05, y: top.y + r * 0.16))
    stem.closeSubpath()
    ctx.addPath(stem)
    ctx.setFillColor(leafDark)
    ctx.fillPath()
}

// MARK: outputs

let root = "StreamingFinder/Assets.xcassets/App Icon & Top Shelf Image.brandassets"

/// Home-screen / App Store icon: three layers of the same size.
func iconLayers(w: Int, h: Int, stack: String, suffix: String) {
    let size = CGSize(width: w, height: h)
    let r = CGFloat(h) * 0.32
    let c = CGPoint(x: size.width / 2, y: size.height * 0.45)
    let back = makeContext(w, h)
    background(back, size, glowAt: c, glowRadius: CGFloat(h) * 0.62)
    save(back, "\(root)/\(stack).imagestack/Back.imagestacklayer/Content.imageset/back\(suffix).png", opaque: true)
    let middle = makeContext(w, h)
    tomatoBody(middle, c: c, r: r)
    save(middle, "\(root)/\(stack).imagestack/Middle.imagestacklayer/Content.imageset/middle\(suffix).png", opaque: false)
    let front = makeContext(w, h)
    tomatoTop(front, c: c, r: r)
    save(front, "\(root)/\(stack).imagestack/Front.imagestacklayer/Content.imageset/front\(suffix).png", opaque: false)
}

/// Top Shelf banner: tomato on the left, name and tagline beside it.
func topShelf(w: Int, h: Int, set: String, file: String) {
    let size = CGSize(width: w, height: h)
    let ctx = makeContext(w, h)
    let r = CGFloat(h) * 0.26
    let c = CGPoint(x: size.width * 0.30, y: size.height * 0.46)
    background(ctx, size, glowAt: c, glowRadius: CGFloat(h) * 0.75)
    tomatoBody(ctx, c: c, r: r)
    tomatoTop(ctx, c: c, r: r)
    let ns = NSGraphicsContext(cgContext: ctx, flipped: false)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = ns
    let title = NSAttributedString(string: "Streaming Finder", attributes: [
        .font: NSFont.systemFont(ofSize: CGFloat(h) * 0.13, weight: .bold), .foregroundColor: NSColor.white])
    let sub = NSAttributedString(string: "Rotten Tomatoes scores for what you already stream", attributes: [
        .font: NSFont.systemFont(ofSize: CGFloat(h) * 0.052, weight: .medium),
        .foregroundColor: NSColor(white: 0.72, alpha: 1)])
    let x = c.x + r * 1.6
    title.draw(at: CGPoint(x: x, y: size.height * 0.50))
    sub.draw(at: CGPoint(x: x + CGFloat(h) * 0.006, y: size.height * 0.38))
    NSGraphicsContext.restoreGraphicsState()
    save(ctx, "\(root)/\(set).imageset/\(file)", opaque: true)
}

iconLayers(w: 400, h: 240, stack: "App Icon", suffix: "")
iconLayers(w: 800, h: 480, stack: "App Icon", suffix: "@2x")
iconLayers(w: 1280, h: 768, stack: "App Icon - App Store", suffix: "")
topShelf(w: 1920, h: 720, set: "Top Shelf Image", file: "topshelf.png")
topShelf(w: 3840, h: 1440, set: "Top Shelf Image", file: "topshelf@2x.png")
topShelf(w: 2320, h: 720, set: "Top Shelf Image Wide", file: "topshelf-wide.png")
topShelf(w: 4640, h: 1440, set: "Top Shelf Image Wide", file: "topshelf-wide@2x.png")
print("wrote \(root)")
