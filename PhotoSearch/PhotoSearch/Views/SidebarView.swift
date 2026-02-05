import SwiftUI

/// Sidebar navigation view.
struct SidebarView: View {
    @Binding var selection: SidebarItem?
    @Binding var selectedFolder: FolderInfo?
    @EnvironmentObject var appState: AppState
    @ObservedObject var libraryViewModel: LibraryViewModel
    var onFolderSelected: ((FolderInfo) -> Void)?

    var body: some View {
        List {
            Section("Library") {
                ForEach(SidebarItem.allCases) { item in
                    HStack {
                        Label(item.rawValue, systemImage: item.icon)
                        Spacer()
                    }
                    .contentShape(Rectangle())
                    .listRowBackground(
                        selection == item && selectedFolder == nil
                            ? Color.accentColor.opacity(0.2)
                            : Color.clear
                    )
                    .onTapGesture {
                        selection = item
                        selectedFolder = nil
                    }
                }
            }

            Section {
                if libraryViewModel.folders.isEmpty {
                    Text("No folders added")
                        .foregroundColor(.secondary)
                        .font(.caption)
                } else {
                    ForEach(libraryViewModel.folders) { folder in
                        FolderRow(folder: folder, libraryViewModel: libraryViewModel)
                            .contentShape(Rectangle())
                            .listRowBackground(
                                selectedFolder?.id == folder.id
                                    ? Color.accentColor.opacity(0.2)
                                    : Color.clear
                            )
                            .onTapGesture {
                                selection = nil
                                selectedFolder = folder
                                onFolderSelected?(folder)
                            }
                            .contextMenu {
                                Button("Index Folder") {
                                    Task {
                                        try? await libraryViewModel.indexFolder(folder)
                                    }
                                }

                                Divider()

                                Button("Remove from Library", role: .destructive) {
                                    libraryViewModel.removeFolder(folder)
                                }
                            }
                    }
                }
            } header: {
                HStack {
                    Text("Folders")
                    Spacer()
                    Button {
                        Task {
                            await libraryViewModel.addFolder()
                        }
                    } label: {
                        Image(systemName: "plus")
                            .font(.caption)
                    }
                    .buttonStyle(.plain)
                    .help("Add Folder")
                }
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
        .alert("Error", isPresented: .constant(libraryViewModel.errorMessage != nil)) {
            Button("OK") {
                libraryViewModel.dismissError()
            }
        } message: {
            Text(libraryViewModel.errorMessage ?? "")
        }
    }
}

// MARK: - Folder Row

struct FolderRow: View {
    let folder: FolderInfo
    @ObservedObject var libraryViewModel: LibraryViewModel

    var body: some View {
        HStack {
            Image(systemName: folder.isIndexed ? "folder.fill" : "folder")
                .foregroundColor(folder.isIndexed ? .blue : .secondary)

            VStack(alignment: .leading, spacing: 2) {
                Text(folder.name)
                    .lineLimit(1)

                Text("\(folder.photoCount) photos")
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }
        }
    }
}

#Preview {
    SidebarView(
        selection: .constant(.allPhotos),
        selectedFolder: .constant(nil),
        libraryViewModel: LibraryViewModel()
    )
    .environmentObject(AppState())
    .frame(width: 220)
}
