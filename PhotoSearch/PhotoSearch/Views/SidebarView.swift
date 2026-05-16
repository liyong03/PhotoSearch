import SwiftUI

/// Sidebar navigation view.
struct SidebarView: View {
    @Binding var selection: SidebarItem?
    @Binding var selectedFolder: FolderInfo?
    @ObservedObject var libraryViewModel: LibraryViewModel
    @ObservedObject var indexingViewModel: IndexingViewModel
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
                        FolderRow(
                            folder: folder,
                            libraryViewModel: libraryViewModel,
                            indexingViewModel: indexingViewModel
                        )
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
                                    indexingViewModel.enqueue(path: folder.path)
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
                            if let folder = libraryViewModel.folders.last {
                                indexingViewModel.enqueue(path: folder.path)
                            }
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
    @ObservedObject var indexingViewModel: IndexingViewModel

    /// The indexing job for this folder in the current batch, if any.
    private var job: IndexJob? {
        indexingViewModel.jobs.first { $0.path == folder.path }
    }

    var body: some View {
        HStack {
            leadingIcon

            VStack(alignment: .leading, spacing: 2) {
                Text(folder.name)
                    .lineLimit(1)

                Text(subtitle)
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }

            Spacer()
        }
    }

    @ViewBuilder
    private var leadingIcon: some View {
        switch job?.status {
        case .indexing:
            ProgressView()
                .controlSize(.small)
        case .waiting:
            Image(systemName: "clock")
                .foregroundColor(.secondary)
        default:
            Image(systemName: folder.isIndexed ? "folder.fill" : "folder")
                .foregroundColor(folder.isIndexed ? .blue : .secondary)
        }
    }

    private var subtitle: String {
        switch job?.status {
        case .waiting:
            return "Waiting to index…"
        case .indexing:
            if let job, job.total > 0 {
                return "Indexing… \(job.processed) of \(job.total)"
            }
            return "Indexing…"
        case .completed:
            if let job, !job.errors.isEmpty {
                return "\(job.succeeded) indexed · \(job.errors.count) failed"
            }
            return "\(folder.photoCount) photos"
        case .failed:
            return "Indexing failed"
        default:
            return "\(folder.photoCount) photos"
        }
    }
}

#Preview {
    SidebarView(
        selection: .constant(.allPhotos),
        selectedFolder: .constant(nil),
        libraryViewModel: LibraryViewModel(),
        indexingViewModel: IndexingViewModel()
    )
    .environmentObject(AppState())
    .frame(width: 220)
}
