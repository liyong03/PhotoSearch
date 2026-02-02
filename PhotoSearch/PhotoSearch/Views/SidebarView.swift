import SwiftUI

/// Sidebar navigation view.
struct SidebarView: View {
    @Binding var selection: SidebarItem?
    @EnvironmentObject var appState: AppState

    var body: some View {
        List(selection: $selection) {
            Section("Library") {
                ForEach(SidebarItem.allCases) { item in
                    Label(item.rawValue, systemImage: item.icon)
                        .tag(item)
                }
            }

            Section("Folders") {
                // Placeholder for user-added folders
                Text("No folders added")
                    .foregroundColor(.secondary)
                    .font(.caption)
            }
        }
        .listStyle(.sidebar)
        .navigationTitle("PhotoSearch")
        .safeAreaInset(edge: .bottom) {
            VStack(alignment: .leading, spacing: 4) {
                Divider()
                HStack {
                    Circle()
                        .fill(appState.isBackendReady ? .green : .red)
                        .frame(width: 8, height: 8)
                    Text(appState.isBackendReady ? "Backend Ready" : "Backend Offline")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .padding(.horizontal)
                .padding(.vertical, 8)
            }
        }
    }
}

#Preview {
    SidebarView(selection: .constant(.allPhotos))
        .environmentObject(AppState())
        .frame(width: 220)
}
