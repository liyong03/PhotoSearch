import Foundation
import os

/// Manages the embedded Python backend server lifecycle.
@MainActor
class BackendManager: ObservableObject {
    /// Shared singleton instance.
    static let shared = BackendManager()

    /// Whether the backend is currently running.
    @Published private(set) var isRunning: Bool = false

    /// The backend process.
    private var process: Process?

    /// Output pipe for logging.
    private var outputPipe: Pipe?

    /// Logger for backend output.
    private let logger = Logger(subsystem: "com.photosearch", category: "Backend")

    /// Port the backend runs on (using unique port to avoid conflicts).
    let port: Int = 52849

    /// Host the backend runs on.
    let host: String = "127.0.0.1"

    /// Backend URL.
    var baseURL: URL {
        URL(string: "http://\(host):\(port)")!
    }

    private init() {}

    // MARK: - Public Methods

    /// Start the backend server.
    func start() {
        guard !isRunning else {
            logger.info("Backend already running")
            return
        }

        logger.info("Attempting to start backend...")
        logger.info("Bundle path: \(Bundle.main.bundlePath)")

        // Check for development mode first
        if let (pythonPath, scriptPath) = findDevelopmentSetup() {
            startWithPython(pythonPath: pythonPath, scriptPath: scriptPath)
            return
        }

        logger.info("No development setup found, checking for bundled backend...")

        // Check for bundled backend
        guard let executableURL = findBundledBackend() else {
            logger.error("Backend executable not found. Make sure the backend is bundled or run from the project directory.")
            logger.error("Searched in bundle: \(Bundle.main.bundlePath)")
            return
        }

        logger.info("Starting bundled backend from: \(executableURL.path)")

        let process = Process()
        process.executableURL = executableURL
        process.environment = ProcessInfo.processInfo.environment
        process.environment?["PHOTOSEARCH_PORT"] = String(port)
        process.environment?["PHOTOSEARCH_HOST"] = host

        // Set up output pipe for logging
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe
        self.outputPipe = pipe

        // Handle output asynchronously
        pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            if !data.isEmpty, let output = String(data: data, encoding: .utf8) {
                self?.logger.info("Backend: \(output)")
            }
        }

        // Handle process termination
        process.terminationHandler = { [weak self] proc in
            Task { @MainActor in
                self?.handleTermination(exitCode: proc.terminationStatus)
            }
        }

        do {
            try process.run()
            self.process = process
            isRunning = true
            logger.info("Backend started with PID: \(process.processIdentifier)")
        } catch {
            logger.error("Failed to start backend: \(error.localizedDescription)")
        }
    }

    /// Start the backend using Python (development mode).
    private func startWithPython(pythonPath: URL, scriptPath: URL) {
        logger.info("Starting backend in development mode")
        logger.info("Python executable: \(pythonPath.path)")
        logger.info("Script path: \(scriptPath.path)")
        logger.info("Working directory: \(scriptPath.deletingLastPathComponent().path)")

        // Verify files exist
        let fileManager = FileManager.default
        guard fileManager.fileExists(atPath: pythonPath.path) else {
            logger.error("Python executable does not exist at: \(pythonPath.path)")
            return
        }
        guard fileManager.fileExists(atPath: scriptPath.path) else {
            logger.error("Script does not exist at: \(scriptPath.path)")
            return
        }

        let process = Process()
        process.executableURL = pythonPath
        process.arguments = [scriptPath.path]
        process.currentDirectoryURL = scriptPath.deletingLastPathComponent()

        // Set environment - inherit PATH for module imports
        var env = ProcessInfo.processInfo.environment
        env["PHOTOSEARCH_PORT"] = String(port)
        env["PHOTOSEARCH_HOST"] = host
        // Add the Backend directory to PYTHONPATH for module resolution
        let backendDir = scriptPath.deletingLastPathComponent().path
        if let existingPythonPath = env["PYTHONPATH"] {
            env["PYTHONPATH"] = "\(backendDir):\(existingPythonPath)"
        } else {
            env["PYTHONPATH"] = backendDir
        }
        process.environment = env

        logger.info("Environment PYTHONPATH: \(env["PYTHONPATH"] ?? "not set")")

        // Set up output pipe
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe
        self.outputPipe = pipe

        pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            if !data.isEmpty, let output = String(data: data, encoding: .utf8) {
                self?.logger.info("Backend output: \(output)")
            }
        }

        process.terminationHandler = { [weak self] proc in
            Task { @MainActor in
                self?.logger.info("Backend process terminated with status: \(proc.terminationStatus)")
                self?.handleTermination(exitCode: proc.terminationStatus)
            }
        }

        do {
            try process.run()
            self.process = process
            isRunning = true
            logger.info("Backend started successfully with PID: \(process.processIdentifier)")
        } catch {
            logger.error("Failed to start backend process: \(error.localizedDescription)")
            logger.error("Error details: \(error)")
        }
    }

    /// Stop the backend server.
    func stop() {
        guard let process = process, isRunning else {
            logger.info("Backend not running")
            return
        }

        logger.info("Stopping backend...")

        // Send SIGTERM for graceful shutdown
        process.terminate()

        // Wait a bit, then force kill if still running
        DispatchQueue.global().asyncAfter(deadline: .now() + 2.0) { [weak self] in
            if process.isRunning {
                self?.logger.warning("Backend didn't stop gracefully, sending SIGKILL")
                process.interrupt()
            }
        }
    }

    /// Restart the backend server.
    func restart() {
        stop()
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) { [weak self] in
            self?.start()
        }
    }

    /// Check if the backend is healthy.
    func checkHealth() async -> Bool {
        // Health endpoint is at /api/v1/health (router has prefix)
        let healthURL = baseURL.appendingPathComponent("api/v1/health")

        do {
            let (_, response) = try await URLSession.shared.data(from: healthURL)
            if let httpResponse = response as? HTTPURLResponse {
                return httpResponse.statusCode == 200
            }
        } catch {
            // Backend not responding
        }

        return false
    }

    // MARK: - Private Methods

    /// Find bundled backend executable (for distributed app).
    private func findBundledBackend() -> URL? {
        // 1. Check inside app bundle (for distributed app)
        if let bundledURL = Bundle.main.url(forResource: "photosearch-backend", withExtension: nil, subdirectory: "Backend") {
            if FileManager.default.isExecutableFile(atPath: bundledURL.path) {
                logger.info("Found bundled backend at: \(bundledURL.path)")
                return bundledURL
            }
        }

        // 2. Check in Resources/Backend directory
        if let resourceURL = Bundle.main.resourceURL?.appendingPathComponent("Backend/photosearch-backend") {
            if FileManager.default.isExecutableFile(atPath: resourceURL.path) {
                logger.info("Found backend in Resources at: \(resourceURL.path)")
                return resourceURL
            }
        }

        return nil
    }

    /// Find development setup (Python + run_server.py).
    private func findDevelopmentSetup() -> (pythonPath: URL, scriptPath: URL)? {
        // For development, look for the Backend directory relative to the app
        let bundlePath = Bundle.main.bundlePath

        // Navigate up from .app bundle to find Backend directory
        var currentPath = URL(fileURLWithPath: bundlePath)

        for _ in 0..<6 {
            currentPath = currentPath.deletingLastPathComponent()
            let backendPath = currentPath.appendingPathComponent("Backend")
            let runServerPath = backendPath.appendingPathComponent("run_server.py")

            if FileManager.default.fileExists(atPath: runServerPath.path) {
                logger.info("Found run_server.py at: \(runServerPath.path)")

                // Check for Python in virtual environment
                if let pythonPath = findPythonInVenv(backendPath: backendPath) {
                    logger.info("Found Python at: \(pythonPath.path)")
                    return (pythonPath, runServerPath)
                }

                // Try system Python as fallback
                if let pythonPath = findSystemPython() {
                    logger.info("Using system Python at: \(pythonPath.path)")
                    return (pythonPath, runServerPath)
                }
            }
        }

        return nil
    }

    private func findPythonInVenv(backendPath: URL) -> URL? {
        // Check for .venv in backend directory
        let venvPython = backendPath.appendingPathComponent(".venv/bin/python")
        if FileManager.default.isExecutableFile(atPath: venvPython.path) {
            return venvPython
        }

        // Check for venv
        let venvPython2 = backendPath.appendingPathComponent("venv/bin/python")
        if FileManager.default.isExecutableFile(atPath: venvPython2.path) {
            return venvPython2
        }

        return nil
    }

    private func findSystemPython() -> URL? {
        // Try common Python locations
        let pythonPaths = [
            "/usr/local/bin/python3",
            "/opt/homebrew/bin/python3",
            "/usr/bin/python3"
        ]

        for path in pythonPaths {
            if FileManager.default.isExecutableFile(atPath: path) {
                return URL(fileURLWithPath: path)
            }
        }

        return nil
    }

    private func handleTermination(exitCode: Int32) {
        isRunning = false
        outputPipe?.fileHandleForReading.readabilityHandler = nil
        outputPipe = nil
        process = nil

        if exitCode != 0 {
            logger.error("Backend terminated with exit code: \(exitCode)")
        } else {
            logger.info("Backend stopped")
        }
    }
}
