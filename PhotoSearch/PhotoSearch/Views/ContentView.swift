import SwiftUI

/// Main content view with sidebar navigation and photo grid.
struct ContentView: View {
    @EnvironmentObject var appState: AppState
    @StateObject private var searchViewModel = SearchViewModel()
    @StateObject private var libraryViewModel = LibraryViewModel()
    @StateObject private var indexingViewModel = IndexingViewModel()
    @State private var selectedSidebarItem: SidebarItem? = .allPhotos
    @State private var selectedFolder: FolderInfo?
    @State private var showFilters: Bool = false
    @State private var selectedPhotoForDetail: SearchResult?
    @State private var showIndexingComplete: Bool = false

    var body: some View {
        NavigationSplitView {
            SidebarView(
                selection: $selectedSidebarItem,
                selectedFolder: $selectedFolder,
                libraryViewModel: libraryViewModel,
                indexingViewModel: indexingViewModel,
                onFolderSelected: { folder in
                    Task {
                        await searchViewModel.browseFolder(folder.path)
                    }
                }
            )
            .navigationSplitViewColumnWidth(min: 180, ideal: 220, max: 300)
        } detail: {
            VStack(spacing: 0) {
                // Search bar
                HStack {
                    SearchBar(text: $searchViewModel.searchQuery, onSubmit: {
                        selectedSidebarItem = nil
                        selectedFolder = nil
                        Task {
                            await searchViewModel.search()
                        }
                    })

                    Button {
                        withAnimation {
                            showFilters.toggle()
                        }
                    } label: {
                        Image(systemName: showFilters ? "line.3.horizontal.decrease.circle.fill" : "line.3.horizontal.decrease.circle")
                    }
                    .buttonStyle(.borderless)
                    .help("Toggle Filters")
                }
                .padding()

                // Filter panel
                if showFilters {
                    FilterPanel(viewModel: searchViewModel)
                    Divider()
                }

                Divider()

                // Main content area
                if searchViewModel.isLoading {
                    LoadingView()
                } else if let error = searchViewModel.errorMessage {
                    SearchErrorView(message: error) {
                        Task {
                            if let folder = selectedFolder {
                                await searchViewModel.browseFolder(folder.path)
                            } else if !searchViewModel.searchQuery.isEmpty {
                                await searchViewModel.search()
                            } else {
                                await searchViewModel.loadAllPhotos()
                            }
                        }
                    }
                } else if searchViewModel.results.isEmpty && !searchViewModel.searchQuery.isEmpty {
                    NoResultsView(query: searchViewModel.searchQuery)
                } else if searchViewModel.results.isEmpty && selectedFolder != nil {
                    EmptyFolderView(folderName: selectedFolder?.name ?? "folder")
                } else if searchViewModel.results.isEmpty {
                    EmptyLibraryView {
                        Task {
                            await addAndIndexFolder()
                        }
                    }
                } else {
                    SearchResultsView(
                        results: searchViewModel.results,
                        totalResults: searchViewModel.totalResults,
                        locationResolved: searchViewModel.locationResolved,
                        folderName: selectedFolder?.name,
                        onPhotoSelected: { photo in
                            selectedPhotoForDetail = photo
                        }
                    )
                }
            }
            .frame(minWidth: 500)
        }
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                if indexingViewModel.isIndexing {
                    IndexingToolbarView(viewModel: indexingViewModel)
                }

                Button {
                    Task {
                        await addAndIndexFolder()
                    }
                } label: {
                    Label("Add Folder", systemImage: "folder.badge.plus")
                }
                .keyboardShortcut("o", modifiers: [.command, .shift])
            }
        }
        // Keyboard shortcut for focusing search (Cmd+F)
        .keyboardShortcut("f", modifiers: .command)
        .onAppear {
            // Set up keyboard shortcut handler
            NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
                if event.modifierFlags.contains(.command) && event.charactersIgnoringModifiers == "f" {
                    NotificationCenter.default.post(name: .focusSearch, object: nil)
                    return nil
                }
                return event
            }
        }
        .task {
            // Load all photos on startup
            await searchViewModel.loadAllPhotos()
        }
        .alert("Error", isPresented: .constant(appState.errorMessage != nil)) {
            Button("OK") {
                appState.dismissError()
            }
        } message: {
            Text(appState.errorMessage ?? "")
        }
        .alert("Indexing Complete", isPresented: $showIndexingComplete) {
            Button("OK") {
                showIndexingComplete = false
            }
        } message: {
            if indexingViewModel.hasErrors {
                Text("Indexed \(indexingViewModel.totalSucceeded) photos. \(indexingViewModel.errors.count) could not be indexed.")
            } else {
                Text("Successfully indexed \(indexingViewModel.totalSucceeded) photos.")
            }
        }
        .sheet(item: $selectedPhotoForDetail) { photo in
            PhotoDetailView(photo: photo)
                .frame(minWidth: 700, minHeight: 500)
        }
        .onReceive(NotificationCenter.default.publisher(for: .indexingComplete)) { _ in
            showIndexingComplete = true
            Task {
                await appState.refreshStatus()
            }
        }
        .onChange(of: selectedSidebarItem) { _, newItem in
            // When "All Photos" is selected, load all photos
            if newItem == .allPhotos {
                selectedFolder = nil
                Task {
                    await searchViewModel.loadAllPhotos()
                }
            }
        }
    }

    // MARK: - Actions

    private func addAndIndexFolder() async {
        await libraryViewModel.addFolder()

        // If a folder was added, queue it for indexing.
        if let folder = libraryViewModel.folders.last {
            indexingViewModel.enqueue(path: folder.path)
        }
    }
}

// MARK: - Sidebar Item Enum

enum SidebarItem: String, Identifiable, CaseIterable {
    case allPhotos = "All Photos"

    var id: String { rawValue }

    var icon: String {
        switch self {
        case .allPhotos: return "photo.on.rectangle"
        }
    }
}

// MARK: - Supporting Views

struct LoadingView: View {
    var body: some View {
        VStack(spacing: 16) {
            ProgressView()
                .scaleEffect(1.5)
            Text("Searching...")
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

struct NoResultsView: View {
    let query: String

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "magnifyingglass")
                .font(.system(size: 48))
                .foregroundColor(.secondary)
            Text("No Results")
                .font(.headline)
            Text("No photos found for \"\(query)\"")
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

struct EmptyLibraryView: View {
    var onAddFolder: (() -> Void)?

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "photo.stack")
                .font(.system(size: 48))
                .foregroundColor(.secondary)
            Text("No Photos")
                .font(.headline)
            Text("Add a folder to start indexing photos.")
                .foregroundColor(.secondary)
            if let onAddFolder = onAddFolder {
                Button("Add Folder") {
                    onAddFolder()
                }
                .buttonStyle(.borderedProminent)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

struct EmptyFolderView: View {
    let folderName: String

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "folder")
                .font(.system(size: 48))
                .foregroundColor(.secondary)
            Text("No Photos in Folder")
                .font(.headline)
            Text("The folder \"\(folderName)\" has no indexed photos.")
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

struct SearchErrorView: View {
    let message: String
    var onRetry: (() -> Void)?

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "exclamationmark.circle")
                .font(.system(size: 48))
                .foregroundColor(.red)
            Text("Search Failed")
                .font(.headline)
            Text(message)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal)
            if let onRetry = onRetry {
                Button("Retry") {
                    onRetry()
                }
                .buttonStyle(.borderedProminent)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

struct SearchResultsView: View {
    let results: [SearchResult]
    let totalResults: Int
    let locationResolved: LocationResolved?
    var folderName: String?
    var onPhotoSelected: ((SearchResult) -> Void)?

    var body: some View {
        VStack(spacing: 0) {
            // Results header
            HStack {
                if let folderName = folderName {
                    Text("\(totalResults) photo\(totalResults == 1 ? "" : "s") in \"\(folderName)\"")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                } else {
                    Text("\(totalResults) result\(totalResults == 1 ? "" : "s")")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                }

                if let location = locationResolved {
                    Spacer()
                    HStack(spacing: 4) {
                        Image(systemName: "location.fill")
                            .font(.caption)
                        Text("Filtered by: \(location.query)")
                            .font(.caption)
                    }
                    .foregroundColor(.blue)
                }

                Spacer()
            }
            .padding(.horizontal)
            .padding(.vertical, 8)

            Divider()

            // Photo grid
            PhotoGridView(photos: results, onPhotoDetail: onPhotoSelected)
        }
    }
}

// MARK: - Indexing Toolbar View

/// Toolbar summary of the indexing queue: a progress bar for the folder
/// currently being indexed, plus a popover listing every queued folder.
struct IndexingToolbarView: View {
    @ObservedObject var viewModel: IndexingViewModel
    @State private var showQueue = false
    @State private var showErrors = false

    var body: some View {
        HStack(spacing: 8) {
            // Determinate bar for the active folder. A plain shape is used
            // instead of ProgressView to avoid AppKit auto-layout warnings
            // in the toolbar.
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 2)
                        .fill(Color.secondary.opacity(0.2))
                    RoundedRectangle(cornerRadius: 2)
                        .fill(Color.accentColor)
                        .frame(width: geo.size.width * max(0, min(1, viewModel.activeJob?.progress ?? 0)))
                }
            }
            .frame(width: 90, height: 6)

            VStack(alignment: .leading, spacing: 2) {
                Text(headline)
                    .font(.caption)
                    .fontWeight(.medium)
                Text(subline)
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }

            if viewModel.hasErrors {
                Button {
                    showErrors.toggle()
                } label: {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundColor(.orange)
                }
                .buttonStyle(.plain)
                .help("\(viewModel.errors.count) photo(s) failed — click for details")
                .popover(isPresented: $showErrors, arrowEdge: .bottom) {
                    IndexingErrorsPopover(errors: viewModel.errors)
                }
            }

            Button {
                showQueue.toggle()
            } label: {
                Image(systemName: "chevron.down")
                    .font(.caption2)
            }
            .buttonStyle(.plain)
            .help("Show indexing queue")
            .popover(isPresented: $showQueue, arrowEdge: .bottom) {
                IndexingQueuePopover(viewModel: viewModel)
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(
            RoundedRectangle(cornerRadius: 6)
                .fill(Color(nsColor: .controlBackgroundColor))
        )
    }

    private var headline: String {
        if let job = viewModel.activeJob {
            return "Indexing \"\(job.name)\""
        }
        return "Indexing…"
    }

    private var subline: String {
        if viewModel.totalFolders > 1 {
            var text = "Folder \(viewModel.currentFolderNumber) of \(viewModel.totalFolders)"
            if viewModel.waitingCount > 0 {
                text += " · \(viewModel.waitingCount) waiting"
            }
            return text
        }
        if let job = viewModel.activeJob, job.total > 0 {
            return "\(job.processed) of \(job.total) photos"
        }
        return "Scanning…"
    }
}

/// Popover listing every folder in the indexing queue with its status.
struct IndexingQueuePopover: View {
    @ObservedObject var viewModel: IndexingViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Indexing Queue")
                .font(.headline)
                .padding(.bottom, 6)

            ForEach(viewModel.jobs) { job in
                IndexJobRow(job: job)
            }

            if viewModel.waitingCount > 0 {
                Divider().padding(.vertical, 6)
                Button("Cancel \(viewModel.waitingCount) waiting folder\(viewModel.waitingCount == 1 ? "" : "s")") {
                    viewModel.cancelPending()
                }
                .buttonStyle(.link)
            }
        }
        .padding(12)
        .frame(width: 280)
    }
}

/// One row in the indexing-queue popover.
struct IndexJobRow: View {
    let job: IndexJob

    var body: some View {
        HStack(spacing: 8) {
            statusIcon
                .frame(width: 16)

            VStack(alignment: .leading, spacing: 1) {
                Text(job.name)
                    .lineLimit(1)
                Text(detail)
                    .font(.caption2)
                    .foregroundColor(detailColor)
            }
            Spacer()
        }
        .padding(.vertical, 3)
    }

    /// A completed folder where some photos failed to index.
    private var completedWithErrors: Bool {
        job.status == .completed && !job.errors.isEmpty
    }

    @ViewBuilder
    private var statusIcon: some View {
        switch job.status {
        case .waiting:
            Image(systemName: "clock")
                .foregroundColor(.secondary)
        case .indexing:
            ProgressView()
                .controlSize(.small)
        case .completed:
            Image(systemName: completedWithErrors
                ? "exclamationmark.triangle.fill"
                : "checkmark.circle.fill")
                .foregroundColor(completedWithErrors ? .orange : .green)
        case .failed:
            Image(systemName: "exclamationmark.circle.fill")
                .foregroundColor(.red)
        }
    }

    private var detailColor: Color {
        completedWithErrors ? .orange : .secondary
    }

    private var detail: String {
        switch job.status {
        case .waiting:
            return "Waiting"
        case .indexing:
            return job.total > 0
                ? "\(job.processed) of \(job.total) · \(Int(job.progress * 100))%"
                : "Scanning…"
        case .completed:
            if completedWithErrors {
                return "\(job.succeeded) indexed · \(job.errors.count) failed"
            }
            return "\(job.succeeded) photo\(job.succeeded == 1 ? "" : "s") indexed"
        case .failed:
            return job.errors.first ?? "Failed"
        }
    }
}

/// Popover listing every photo that failed to index, with the reason.
struct IndexingErrorsPopover: View {
    let errors: [String]

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Indexing Errors")
                .font(.headline)
                .padding(.bottom, 6)

            Text("\(errors.count) photo\(errors.count == 1 ? "" : "s") could not be indexed.")
                .font(.caption)
                .foregroundColor(.secondary)
                .padding(.bottom, 8)

            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(Array(errors.enumerated()), id: \.offset) { _, err in
                        HStack(alignment: .top, spacing: 6) {
                            Image(systemName: "exclamationmark.circle.fill")
                                .foregroundColor(.orange)
                                .font(.caption)
                            Text(err)
                                .font(.caption)
                                .textSelection(.enabled)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
            }
            .frame(maxHeight: 240)
        }
        .padding(12)
        .frame(width: 380)
    }
}

// MARK: - Preview

#Preview {
    ContentView()
        .environmentObject(AppState())
}
