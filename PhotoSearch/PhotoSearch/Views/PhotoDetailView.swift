import SwiftUI
import QuickLook

/// Detailed view for a single photo with metadata.
struct PhotoDetailView: View {
    let photo: SearchResult
    @Environment(\.dismiss) private var dismiss
    @State private var image: NSImage?
    @State private var isLoadingImage: Bool = true
    @State private var quickLookURL: URL?

    var body: some View {
        HSplitView {
            // Image preview
            imagePreview
                .frame(minWidth: 400)

            // Metadata panel
            metadataPanel
                .frame(width: 300)
        }
        .frame(minWidth: 700, minHeight: 500)
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                Button {
                    quickLookURL = URL(fileURLWithPath: photo.path)
                } label: {
                    Label("Quick Look", systemImage: "eye")
                }
                .keyboardShortcut(" ", modifiers: [])

                Button {
                    openInPreview()
                } label: {
                    Label("Open in Preview", systemImage: "arrow.up.forward.square")
                }
                .keyboardShortcut(.return, modifiers: [])

                Button {
                    revealInFinder()
                } label: {
                    Label("Reveal in Finder", systemImage: "folder")
                }
                .keyboardShortcut("r", modifiers: .command)
            }
        }
        .quickLookPreview($quickLookURL)
        .task {
            await loadImage()
        }
    }

    // MARK: - Image Preview

    private var imagePreview: some View {
        ZStack {
            Color(nsColor: .windowBackgroundColor)

            if isLoadingImage {
                ProgressView()
                    .scaleEffect(1.5)
            } else if let image = image {
                Image(nsImage: image)
                    .resizable()
                    .aspectRatio(contentMode: .fit)
                    .padding()
            } else {
                VStack(spacing: 12) {
                    Image(systemName: "photo")
                        .font(.system(size: 64))
                        .foregroundColor(.secondary)
                    Text("Unable to load image")
                        .foregroundColor(.secondary)
                }
            }
        }
    }

    // MARK: - Metadata Panel

    private var metadataPanel: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Filename
                metadataSection(title: "File") {
                    metadataRow(label: "Name", value: URL(fileURLWithPath: photo.path).lastPathComponent)
                    metadataRow(label: "Path", value: photo.path, copyable: true)
                }

                // Description
                if let description = photo.description, !description.isEmpty {
                    metadataSection(title: "Description") {
                        Text(description)
                            .font(.body)
                            .foregroundColor(.primary)
                    }
                }

                // Score
                if let score = photo.score {
                    metadataSection(title: "Match") {
                        HStack {
                            Text("Relevance")
                                .foregroundColor(.secondary)
                            Spacer()
                            Text("\(Int(score * 100))%")
                                .fontWeight(.medium)
                                .foregroundColor(scoreColor(score))
                        }

                        ProgressView(value: score)
                            .tint(scoreColor(score))
                    }
                }

                // Date
                if let timestamp = photo.timestamp {
                    metadataSection(title: "Date") {
                        metadataRow(label: "Taken", value: formatDate(timestamp))
                    }
                }

                // Location
                if hasLocation {
                    metadataSection(title: "Location") {
                        if let city = photo.city {
                            metadataRow(label: "City", value: city)
                        }
                        if let state = photo.state {
                            metadataRow(label: "State", value: state)
                        }
                        if let country = photo.country {
                            metadataRow(label: "Country", value: country)
                        }
                    }
                }

                Spacer()
            }
            .padding()
        }
        .background(Color(nsColor: .controlBackgroundColor))
    }

    // MARK: - Metadata Helpers

    private func metadataSection<Content: View>(title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.headline)
                .foregroundColor(.primary)

            content()
        }
    }

    private func metadataRow(label: String, value: String, copyable: Bool = false) -> some View {
        HStack(alignment: .top) {
            Text(label)
                .foregroundColor(.secondary)
                .frame(width: 60, alignment: .leading)

            if copyable {
                Text(value)
                    .foregroundColor(.primary)
                    .lineLimit(2)
                    .truncationMode(.middle)
                    .textSelection(.enabled)
            } else {
                Text(value)
                    .foregroundColor(.primary)
            }
        }
        .font(.callout)
    }

    private var hasLocation: Bool {
        photo.city != nil || photo.state != nil || photo.country != nil
    }

    private func formatDate(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateStyle = .long
        formatter.timeStyle = .short
        return formatter.string(from: date)
    }

    private func scoreColor(_ score: Double) -> Color {
        if score >= 0.8 {
            return .green
        } else if score >= 0.5 {
            return .orange
        } else {
            return .red
        }
    }

    // MARK: - Actions

    private func loadImage() async {
        isLoadingImage = true
        defer { isLoadingImage = false }

        let url = URL(fileURLWithPath: photo.path)

        // Load image on background thread
        let loadedImage = await Task.detached(priority: .userInitiated) {
            NSImage(contentsOf: url)
        }.value

        await MainActor.run {
            self.image = loadedImage
        }
    }

    private func openInPreview() {
        let url = URL(fileURLWithPath: photo.path)
        NSWorkspace.shared.open(url)
    }

    private func revealInFinder() {
        let url = URL(fileURLWithPath: photo.path)
        NSWorkspace.shared.activateFileViewerSelecting([url])
    }
}

// MARK: - Photo Detail Window

/// Opens a photo detail view in a new window.
struct PhotoDetailWindow: View {
    let photo: SearchResult

    var body: some View {
        PhotoDetailView(photo: photo)
            .navigationTitle(URL(fileURLWithPath: photo.path).lastPathComponent)
    }
}

// MARK: - Preview

#Preview {
    PhotoDetailView(photo: SearchResult(
        id: "1",
        path: "/Users/Shared/test.jpg",
        score: 0.95,
        description: "A beautiful sunset over the ocean with golden clouds reflecting on the water",
        timestamp: Date(),
        city: "Honolulu",
        state: "Hawaii",
        country: "USA"
    ))
    .frame(width: 800, height: 600)
}
