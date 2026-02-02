import SwiftUI

/// Main entry point for the PhotoSearch macOS app.
/// Initializes the app and manages the backend lifecycle.
@main
struct PhotoSearchApp: App {
    @StateObject private var appState = AppState()

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
        }
    }
}

/// Notification name for focusing the search field.
extension Notification.Name {
    static let focusSearch = Notification.Name("focusSearch")
}
