import AppKit

let size = NSSize(width: 1024, height: 1024)
func shade(_ red: CGFloat, _ green: CGFloat, _ blue: CGFloat, _ alpha: CGFloat = 1) -> NSColor {
    NSColor(srgbRed: red, green: green, blue: blue, alpha: alpha)
}

let image = NSImage(size: size, flipped: false) { _ in
    let rect = NSRect(x: 76, y: 76, width: 872, height: 872)
    let bezel = NSBezierPath(roundedRect: rect, xRadius: 210, yRadius: 210)
    NSGraphicsContext.saveGraphicsState()
    bezel.addClip()
    NSGradient(starting: shade(0.99, 0.98, 1), ending: shade(0.86, 0.83, 1))?.draw(in: rect, angle: -55)
    let violet = NSPoint(x: 765, y: 537)
    NSGradient(starting: shade(0.53, 0.58, 1, 0.76), ending: shade(0.53, 0.58, 1, 0))?.draw(
        fromCenter: violet, radius: 12, toCenter: violet, radius: 557, options: [.drawsBeforeStartingLocation]
    )
    let rose = NSPoint(x: 850, y: 148)
    NSGradient(starting: shade(1, 0.66, 0.75, 0.76), ending: shade(1, 0.66, 0.75, 0))?.draw(
        fromCenter: rose, radius: 0, toCenter: rose, radius: 416, options: [.drawsBeforeStartingLocation]
    )
    for scale in [CGFloat(1), CGFloat(0.77)] {
        let orbit = NSBezierPath(ovalIn: NSRect(x: -340 * scale, y: -184 * scale, width: 680 * scale, height: 368 * scale))
        var transform = AffineTransform()
        transform.rotate(byDegrees: 35)
        transform.translate(x: 719, y: 311)
        orbit.transform(using: transform)
        shade(1, 1, 1, 0.72).setStroke()
        orbit.lineWidth = 5
        orbit.stroke()
    }
    NSGraphicsContext.restoreGraphicsState()
    shade(1, 1, 1, 0.82).setStroke()
    bezel.lineWidth = 7
    bezel.stroke()

    let letter: NSString = "S"
    let attributes: [NSAttributedString.Key: Any] = [
        .font: NSFont.systemFont(ofSize: 552, weight: .black),
        .foregroundColor: shade(0.09, 0.105, 0.19)
    ]
    let measured = letter.size(withAttributes: attributes)
    letter.draw(at: NSPoint(x: (1024 - measured.width) / 2 - 49, y: (1024 - measured.height) / 2 + 12), withAttributes: attributes)
    let dot = NSBezierPath(ovalIn: NSRect(x: 667, y: 321, width: 99, height: 99))
    NSGradient(starting: shade(0.28, 0.31, 0.8), ending: shade(0.76, 0.36, 0.67))?.draw(in: dot, angle: -49)
    return true
}
guard let source = image.tiffRepresentation, let bitmap = NSBitmapImageRep(data: source),
      let png = bitmap.representation(using: .png, properties: [:]) else { fatalError("Could not draw the icon") }
try png.write(to: URL(fileURLWithPath: CommandLine.arguments[1]))
