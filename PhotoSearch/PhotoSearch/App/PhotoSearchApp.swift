import SwiftUI

/// Main entry point for the PhotoSearch macOS app.
/// Initializes the app and manages the backend lifecycle.
@main
struct PhotoSearchApp: App {
    @StateObject private var appState = AppState()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(appState)
                .frame(minWidth: 800, minHeight: 600)
        }
        .windowStyle(.automatic)
        .commands {
            // Search command
            CommandGroup(after: .textEditing) {
                Button("Find...") {
                    NotificationCenter.default.post(name: .focusSearch, object: nil)
                }
                .keyboardShortcut("f", modifiers: .command)
            }

            // Sidebar toggle
            SidebarCommands()

            // Backend commands (for debugging)
            CommandGroup(after: .appInfo) {
                Button("Restart Backend") {
                    Task {
                        await appState.restartBackend()
                    }
                }

                Divider()
            }
        }
        .onChange(of: scenePhase) { _, newPhase in
            if newPhase == .background {
                // App is going to background - could stop backend to save resources
                // For now, keep it running
            }
        }
    }

    init() {
        // Register for app termination to clean up backend
        NotificationCenter.default.addObserver(
            forName: NSApplication.willTerminateNotification,
            object: nil,
            queue: .main
        ) { _ in
            // Stop the backend when app terminates
            Task { @MainActor in
                AppState().stopBackend()
            }
        }
    }
}

/// Notification name for focusing the search field.
extension Notification.Name {
    static let focusSearch = Notification.Name("focusSearch")
}
