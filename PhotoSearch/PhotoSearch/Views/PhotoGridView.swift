import SwiftUI
import QuickLook

/// Grid view displaying photo thumbnails with keyboard navigation.
struct PhotoGridView: View {
    let photos: [SearchResult]
    var onPhotoDetail: ((SearchResult) -> Void)?

    @State private var selectedPhotoID: String?
    @State private var selectedIndex: Int = 0
    @State private var quickLookURL: URL?
    @FocusState private var isFocused: Bool

    /// Number of columns (calculated based on available width)
    private let columns = [
        GridItem(.adaptive(minimum: 150, maximum: 200), spacing: 12)
    ]

    var body: some View {
        ScrollViewReader { scrollProxy in
            ScrollView {
                LazyVGrid(columns: columns, spacing: 12) {
                    ForEach(Array(photos.enumerated()), id: \.element.id) { index, photo in
                        PhotoThumbnailView(
                            photo: photo,
                            isSelected: selectedPhotoID == photo.id,
                            onSelect: {
                                selectPhoto(at: index)
                            },
                            onDoubleClick: {
                                showPhotoDetail(photo)
                            }
                        )
                        .id(photo.id)
                        .contextMenu {
                            Button("Show Details") {
                                showPhotoDetail(photo)
                            }

                            Button("Quick Look") {
                                quickLookURL = URL(fileURLWithPath: photo.path)
                            }
                            .keyboardShortcut(" ", modifiers: [])

                            Divider()

                            Button("Open in Preview") {
                                openPhoto(photo)
                            }

                            Button("Reveal in Finder") {
                                revealInFinder(photo)
                            }
                        }
                    }
                }
                .padding()
            }
            .background(Color(nsColor: .textBackgroundColor))
            .focusable()
            .focused($isFocused)
            .onKeyPress(.leftArrow) {
                navigateLeft()
                scrollToSelected(proxy: scrollProxy)
                return .handled
            }
            .onKeyPress(.rightArrow) {
                navigateRight()
                scrollToSelected(proxy: scrollProxy)
                return .handled
            }
            .onKeyPress(.upArrow) {
                navigateUp()
                scrollToSelected(proxy: scrollProxy)
                return .handled
            }
            .onKeyPress(.downArrow) {
                navigateDown()
                scrollToSelected(proxy: scrollProxy)
                return .handled
            }
            .onKeyPress(.space) {
                showQuickLook()
                return .handled
            }
            .onKeyPress(.return) {
                openSelectedPhoto()
                return .handled
            }
            .onChange(of: photos) { _, newPhotos in
                // Reset selection when photos change
                if !newPhotos.isEmpty {
                    selectedIndex = 0
                    selectedPhotoID = newPhotos.first?.id
                } else {
                    selectedPhotoID = nil
                }
            }
            .onAppear {
                // Set initial selection
                if selectedPhotoID == nil && !photos.isEmpty {
                    selectedPhotoID = photos.first?.id
                    selectedIndex = 0
                }
                isFocused = true
            }
        }
        .quickLookPreview($quickLookURL)
    }

    // MARK: - Quick Look

    private func showQuickLook() {
        guard let photo = selectedPhoto else { return }
        quickLookURL = URL(fileURLWithPath: photo.path)
    }

    // MARK: - Navigation

    private var selectedPhoto: SearchResult? {
        photos.first { $0.id == selectedPhotoID }
    }

    private func selectPhoto(at index: Int) {
        guard index >= 0 && index < photos.count else { return }
        selectedIndex = index
        selectedPhotoID = photos[index].id
    }

    private func navigateLeft() {
        if selectedIndex > 0 {
            selectPhoto(at: selectedIndex - 1)
        }
    }

    private func navigateRight() {
        if selectedIndex < photos.count - 1 {
            selectPhoto(at: selectedIndex + 1)
        }
    }

    private func navigateUp() {
        // Move up one row (assuming ~4 items per row as approximation)
        let columnsPerRow = estimatedColumnsPerRow
        let newIndex = selectedIndex - columnsPerRow
        if newIndex >= 0 {
            selectPhoto(at: newIndex)
        }
    }

    private func navigateDown() {
        // Move down one row
        let columnsPerRow = estimatedColumnsPerRow
        let newIndex = selectedIndex + columnsPerRow
        if newIndex < photos.count {
            selectPhoto(at: newIndex)
        }
    }

    /// Estimated number of columns per row (will vary based on window width)
    private var estimatedColumnsPerRow: Int {
        4 // Approximate value; could be calculated from view width
    }

    private func scrollToSelected(proxy: ScrollViewProxy) {
        guard let selectedPhotoID = selectedPhotoID else { return }
        withAnimation(.easeInOut(duration: 0.2)) {
            proxy.scrollTo(selectedPhotoID, anchor: .center)
        }
    }

    private func openPhoto(_ photo: SearchResult) {
        let url = URL(fileURLWithPath: photo.path)
        NSWorkspace.shared.open(url)
    }

    private func openSelectedPhoto() {
        guard let photo = selectedPhoto else { return }
        openPhoto(photo)
    }

    private func showPhotoDetail(_ photo: SearchResult) {
        onPhotoDetail?(photo)
    }

    private func showSelectedPhotoDetail() {
        guard let photo = selectedPhoto else { return }
        showPhotoDetail(photo)
    }

    private func revealInFinder(_ photo: SearchResult) {
        let url = URL(fileURLWithPath: photo.path)
        NSWorkspace.shared.activateFileViewerSelecting([url])
    }
}

// MARK: - Empty Grid View

struct EmptyGridView: View {
    let message: String
    let systemImage: String

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: systemImage)
                .font(.system(size: 48))
                .foregroundColor(.secondary)
            Text(message)
                .font(.headline)
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

// MARK: - Grid Size Preference

/// Preference key for tracking grid item size
struct GridItemSizePreferenceKey: PreferenceKey {
    static var defaultValue: CGSize = .zero

    static func reduce(value: inout CGSize, nextValue: () -> CGSize) {
        value = nextValue()
    }
}

// MARK: - Preview

#Preview("With Photos") {
    PhotoGridView(photos: [
        SearchResult(id: "1", path: "/path/to/photo1.jpg", score: 0.95, description: "A beautiful sunset over the ocean", timestamp: Date(), city: "Honolulu", state: "Hawaii", country: "USA"),
        SearchResult(id: "2", path: "/path/to/photo2.jpg", score: 0.85, description: "Mountain landscape with snow-capped peaks", timestamp: nil, city: "Denver", state: "Colorado", country: "USA"),
        SearchResult(id: "3", path: "/path/to/photo3.jpg", score: 0.75, description: "City skyline at night", timestamp: Date(), city: "New York", state: nil, country: "USA"),
        SearchResult(id: "4", path: "/path/to/photo4.jpg", score: 0.65, description: "Beach with palm trees", timestamp: nil, city: "Miami", state: "Florida", country: "USA"),
    ])
    .frame(width: 800, height: 600)
}

#Preview("Empty") {
    EmptyGridView(message: "No photos found", systemImage: "photo.on.rectangle")
        .frame(width: 400, height: 300)
}
