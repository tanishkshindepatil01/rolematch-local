import AppKit
import Darwin
import WebKit

@main
final class Desktop: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate {
    private var window: NSWindow!
    private var webView: WKWebView!
    private var backend: Process?
    private var output: Pipe?
    private var startupLog = ""
    private var localURL: URL?
    private var downloadDestinations: [ObjectIdentifier: URL] = [:]
    private var stopping = false
    private var loaded = false
    private let portfolio = CommandLine.arguments.contains("--portfolio")

    static func main() {
        let application = NSApplication.shared
        let delegate = Desktop()
        application.delegate = delegate
        application.setActivationPolicy(.regular)
        application.run()
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        setupMenu()
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .nonPersistent()
        webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.underPageBackgroundColor = NSColor(srgbRed: 0.98, green: 0.98, blue: 1, alpha: 1)

        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1110, height: 810),
            styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false
        )
        window.title = portfolio ? "RoleMatch Local · Portfolio Demo" : "RoleMatch Local"
        window.isReleasedWhenClosed = false
        window.contentView = webView
        window.minSize = NSSize(width: 440, height: 500)
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)

        showPage("Starting RoleMatch Local", "Setting up the local app. The first launch may take a moment.")
        startBackend()
    }

    private func setupMenu() {
        let main = NSMenu()
        let appItem = NSMenuItem()
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "Quit RoleMatch Local", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu
        main.addItem(appItem)

        let fileItem = NSMenuItem()
        let fileMenu = NSMenu(title: "File")
        fileMenu.addItem(withTitle: "Close Window", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")
        fileItem.submenu = fileMenu
        main.addItem(fileItem)

        let editItem = NSMenuItem()
        let editMenu = NSMenu(title: "Edit")
        for (title, action, key) in [("Copy", "copy:", "c"), ("Paste", "paste:", "v"), ("Select All", "selectAll:", "a")] {
            editMenu.addItem(withTitle: title, action: Selector(action), keyEquivalent: key)
        }
        editItem.submenu = editMenu
        main.addItem(editItem)
        NSApp.mainMenu = main
    }

    private func startBackend() {
        let root = Bundle.main.bundleURL.deletingLastPathComponent()
        let launcher = root.appendingPathComponent("launcher/server.sh")
        guard FileManager.default.isReadableFile(atPath: launcher.path) else {
            showPage("RoleMatch Local files missing", "Keep RoleMatch Local.app inside the project folder, then open it again.")
            return
        }
        guard let port = availablePort(), let address = URL(string: "http://127.0.0.1:\(port)") else {
            showPage("Could not start RoleMatch Local", "The Mac could not open a local port. Close this window and try again.")
            return
        }
        localURL = address

        var environment = ProcessInfo.processInfo.environment
        environment["ROLEMATCH_VIEW"] = portfolio ? "portfolio" : "jobs"
        environment["ROLEMATCH_APP_PORT"] = String(port)
        environment["ROLEMATCH_NO_BROWSER"] = "1"
        if portfolio, let ollamaPort = availablePort(), ollamaPort != port {
            environment["ROLEMATCH_OLLAMA_PORT"] = String(ollamaPort)
        }

        let process = Process()
        let pipe = Pipe()
        process.executableURL = URL(fileURLWithPath: "/bin/bash")
        process.arguments = [launcher.path]
        process.currentDirectoryURL = root
        process.environment = environment
        process.standardOutput = pipe
        process.standardError = pipe
        pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            if data.isEmpty {
                handle.readabilityHandler = nil
                return
            }
            DispatchQueue.main.async { self?.receive(data) }
        }
        process.terminationHandler = { [weak self] _ in
            DispatchQueue.main.async { self?.backendExited() }
        }
        do {
            try process.run()
            backend = process
            output = pipe
        } catch {
            pipe.fileHandleForReading.readabilityHandler = nil
            showPage("Could not start RoleMatch Local", error.localizedDescription)
        }
    }

    private func availablePort() -> UInt16? {
        let descriptor = socket(AF_INET, SOCK_STREAM, 0)
        guard descriptor >= 0 else { return nil }
        defer { close(descriptor) }
        var address = sockaddr_in()
        address.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        address.sin_family = sa_family_t(AF_INET)
        address.sin_addr = in_addr(s_addr: in_addr_t(INADDR_LOOPBACK).bigEndian)
        var length = socklen_t(MemoryLayout<sockaddr_in>.size)
        let bound = withUnsafeMutablePointer(to: &address) { pointer in
            pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { socketAddress in
                Darwin.bind(descriptor, socketAddress, length) == 0 && getsockname(descriptor, socketAddress, &length) == 0
            }
        }
        return bound ? UInt16(bigEndian: address.sin_port) : nil
    }

    private func receive(_ data: Data) {
        guard !loaded, !stopping, let url = localURL else { return }
        startupLog += String(decoding: data, as: UTF8.self)
        if startupLog.contains("RoleMatch Local is running at \(url.absoluteString).") {
            loaded = true
            webView.load(URLRequest(url: url))
        } else {
            startupLog = String(startupLog.suffix(8000))
        }
    }

    private func backendExited() {
        backend = nil
        if stopping {
            NSApp.reply(toApplicationShouldTerminate: true)
        } else {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) { [weak self] in
                guard let self, !self.stopping else { return }
                let lines = self.startupLog.split(whereSeparator: \.isNewline).suffix(5).joined(separator: "\n")
                let message = self.loaded || lines.isEmpty ? "Close this window and open RoleMatch Local again." : lines
                self.showPage(self.loaded ? "RoleMatch Local stopped" : "Could not start RoleMatch Local", message)
            }
        }
    }

    private func showPage(_ title: String, _ message: String) {
        let safeMessage = message.replacingOccurrences(of: "&", with: "&amp;")
            .replacingOccurrences(of: "<", with: "&lt;").replacingOccurrences(of: ">", with: "&gt;")
        webView.loadHTMLString("""
            <!doctype html><html><meta name="viewport" content="width=device-width,initial-scale=1">
            <style>body{background:radial-gradient(ellipse at 85% 60%,#d9d8ff,transparent 62%),#faf9ff;
            color:#171b30;font:17px -apple-system,sans-serif;padding:12vh 9vw;min-height:70vh}
            strong{letter-spacing:-.05em}span{color:#5961cb}h1{font-size:clamp(2rem,7vw,4rem);letter-spacing:-.06em}
            p{color:#526078;white-space:pre-wrap;line-height:1.55}</style>
            <strong>RoleMatch Local<span>.</span></strong><h1>\(title)</h1><p>\(safeMessage)</p></html>
            """, baseURL: nil)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard let backend, backend.isRunning else { return .terminateNow }
        stopping = true
        backend.terminate()
        return .terminateLater
    }

    private func isLocal(_ url: URL) -> Bool {
        url.scheme == "http" && url.host == localURL?.host && url.port == localURL?.port
    }

    private func isLocalDownload(_ url: URL) -> Bool {
        if isLocal(url) { return true }
        guard url.scheme == "blob", let origin = URL(string: String(url.absoluteString.dropFirst(5))) else { return false }
        return isLocal(origin)
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url else { decisionHandler(.cancel); return }
        if navigationAction.shouldPerformDownload && isLocalDownload(url) {
            decisionHandler(.download)
        } else if isLocal(url) || url.scheme == "about" {
            decisionHandler(.allow)
        } else {
            if url.scheme == "https", navigationAction.navigationType == .linkActivated { NSWorkspace.shared.open(url) }
            decisionHandler(.cancel)
        }
    }

    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = navigationAction.request.url {
            if navigationAction.shouldPerformDownload && isLocalDownload(url) {
                webView.startDownload(using: navigationAction.request) { download in download.delegate = self }
            } else if isLocal(url) { webView.load(navigationAction.request) }
            else if url.scheme == "https" { NSWorkspace.shared.open(url) }
        }
        return nil
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationResponse: WKNavigationResponse,
                 decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        if let url = navigationResponse.response.url, isLocalDownload(url),
           ["application/pdf", "application/zip", "application/x-tex"].contains(navigationResponse.response.mimeType ?? "") {
            decisionHandler(.download)
        } else {
            decisionHandler(.allow)
        }
    }

    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) {
        download.delegate = self
    }

    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) {
        download.delegate = self
    }

    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse, suggestedFilename: String,
                  completionHandler: @escaping (URL?) -> Void) {
        let files = FileManager.default
        guard let directory = files.urls(for: .downloadsDirectory, in: .userDomainMask).first else {
            completionHandler(nil)
            return
        }
        let safeName = (suggestedFilename as NSString).lastPathComponent
        let fileName = safeName as NSString
        let reportedExtension = fileName.pathExtension.lowercased()
        let extensionByType = ["application/pdf": "pdf", "application/zip": "zip", "application/x-tex": "tex"]
        guard let fileExtension = ["pdf", "zip", "tex"].contains(reportedExtension) ? reportedExtension : extensionByType[response.mimeType ?? ""] else {
            completionHandler(nil)
            return
        }
        let stem = reportedExtension == fileExtension ? fileName.deletingPathExtension : "Tailored-CV"
        var destination = directory.appendingPathComponent("\(stem).\(fileExtension)")
        var number = 2
        while files.fileExists(atPath: destination.path) || downloadDestinations.values.contains(destination) {
            destination = directory.appendingPathComponent("\(stem)-\(number).\(fileExtension)")
            number += 1
        }
        downloadDestinations[ObjectIdentifier(download)] = destination
        completionHandler(destination)
    }

    func downloadDidFinish(_ download: WKDownload) {
        if let destination = downloadDestinations.removeValue(forKey: ObjectIdentifier(download)) {
            NSWorkspace.shared.activateFileViewerSelecting([destination])
        }
    }

    func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {
        downloadDestinations.removeValue(forKey: ObjectIdentifier(download))
        guard !stopping else { return }
        let alert = NSAlert(error: error)
        alert.beginSheetModal(for: window)
    }

    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = parameters.allowsDirectories
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.beginSheetModal(for: window) { result in
            completionHandler(result == .OK ? panel.urls : nil)
        }
    }
}
