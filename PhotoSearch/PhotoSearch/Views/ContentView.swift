import SwiftUI

/// Main content view with sidebar navigation and photo grid.
struct ContentView: View {
    @EnvironmentObject var appState: AppState
    @StateObject private var searchViewModel = SearchViewModel()
    @StateObject private var libraryViewModel = LibraryViewModel()
    @State private var selectedSidebarItem: SidebarItem? = .allPhotos
    @State private var showFilters: Bool = false

    var body: some View {
        NavigationSplitView {
            SidebarView(selection: $selectedSidebarItem, libraryViewModel: libraryViewModel)
                .navigationSplitViewColumnWidth(min: 180, ideal: 220, max: 300)
        } detail: {
            VStack(spacing: 0) {
                // Search bar
                HStack {
                    SearchBar(text: $searchViewModel.searchQuery, onSubmit: {
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
                if !appState.isBackendReady {
                    BackendNotReadyView()
                } else if searchViewModel.isLoading {
                    LoadingView()
                } else if let error = searchViewModel.errorMessage {
                    SearchErrorView(message: error) {
                        Task {
                            await searchViewModel.search()
                        }
                    }
                } else if searchViewModel.results.isEmpty && !searchViewModel.searchQuery.isEmpty {
                    NoResultsView(query: searchViewModel.searchQuery)
                } else if searchViewModel.results.isEmpty {
                    EmptyLibraryView {
                        Task {
                            await libraryViewModel.addFolder()
                        }
                    }
                } else {
                    SearchResultsView(
                        results: searchViewModel.results,
                        totalResults: searchViewModel.totalResults,
                        locationResolved: searchViewModel.locationResolved
                    )
                }
            }
            .frame(minWidth: 500)
        }
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                if appState.isIndexing {
                    IndexingProgressView(progress: appState.indexingProgress)
                }

                Button {
                    Task {
                        await libraryViewModel.addFolder()
                    }
                } label: {
                    Label("Add Folder", systemImage: "folder.badge.plus")
                }

                Button {
                    Task {
                        await appState.checkBackendStatus()
                    }
                } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
            }
        }
        .alert("Error", isPresented: .constant(appState.errorMessage != nil)) {
            Button("OK") {
                appState.dismissError()
            }
        } message: {
            Text(appState.errorMessage ?? "")
        }
        .onReceive(NotificationCenter.default.publisher(for: .focusSearch)) { _ in
            // Focus search field
        }
    }
}

// MARK: - Sidebar Item Enum

enum SidebarItem: String, Identifiable, CaseIterable {
    case allPhotos = "All Photos"
    case recent = "Recent"
    case folders = "Folders"

    var id: String { rawValue }

    var icon: String {
        switch self {
        case .allPhotos: return "photo.on.rectangle"
        case .recent: return "clock"
        case .folders: return "folder"
        }
    }
}

// MARK: - Supporting Views

struct BackendNotReadyView: View {
    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "exclamationmark.triangle")
                .font(.system(size: 48))
                .foregroundColor(.orange)
            Text("Backend Not Available")
                .font(.headline)
            Text("Please start the PhotoSearch backend server.")
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

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

struct IndexingProgressView: View {
    let progress: Double

    var body: some View {
        HStack(spacing: 8) {
            ProgressView(value: progress)
                .progressViewStyle(.linear)
                .frame(width: 100)
            Text("\(Int(progress * 100))%")
                .font(.caption)
                .monospacedDigit()
        }
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

    var body: some View {
        VStack(spacing: 0) {
            // Results header
            HStack {
                Text("\(totalResults) result\(totalResults == 1 ? "" : "s")")
                    .font(.subheadline)
                    .foregroundColor(.secondary)

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
            PhotoGridView(photos: results)
        }
    }
}

// MARK: - Preview

#Preview {
    ContentView()
        .environmentObject(AppState())
}
