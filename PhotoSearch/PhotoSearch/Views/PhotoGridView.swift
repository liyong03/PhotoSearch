import SwiftUI

/// Grid view displaying photo thumbnails.
struct PhotoGridView: View {
    let photos: [SearchResult]

    @State private var selectedPhotoID: String?

    private let columns = [
        GridItem(.adaptive(minimum: 150, maximum: 200), spacing: 12)
    ]

    var body: some View {
        ScrollView {
            LazyVGrid(columns: columns, spacing: 12) {
                ForEach(photos) { photo in
                    PhotoThumbnailView(photo: photo, isSelected: selectedPhotoID == photo.id)
                        .onTapGesture {
                            selectedPhotoID = photo.id
                        }
                        .onTapGesture(count: 2) {
                            openPhoto(photo)
                        }
                }
            }
            .padding()
        }
        .background(Color(nsColor: .textBackgroundColor))
    }

    private func openPhoto(_ photo: SearchResult) {
        // Open in Quick Look or default app
        let url = URL(fileURLWithPath: photo.path)
        NSWorkspace.shared.open(url)
    }
}

/// Individual photo thumbnail view.
struct PhotoThumbnailView: View {
    let photo: SearchResult
    let isSelected: Bool

    @StateObject private var thumbnailLoader = ThumbnailLoader()

    var body: some View {
        VStack(spacing: 4) {
            ZStack {
                Rectangle()
                    .fill(Color(nsColor: .separatorColor))
                    .aspectRatio(1, contentMode: .fit)

                if let image = thumbnailLoader.image {
                    Image(nsImage: image)
                        .resizable()
                        .aspectRatio(contentMode: .fill)
                        .frame(minWidth: 0, maxWidth: .infinity, minHeight: 0, maxHeight: .infinity)
                        .clipped()
                } else {
                    ProgressView()
                }
            }
            .cornerRadius(8)
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(isSelected ? Color.accentColor : Color.clear, lineWidth: 3)
            )
            .shadow(color: .black.opacity(0.1), radius: 2, x: 0, y: 1)

            // Photo info
            VStack(alignment: .leading, spacing: 2) {
                if let description = photo.description {
                    Text(description)
                        .font(.caption)
                        .lineLimit(2)
                        .foregroundColor(.primary)
                }

                HStack(spacing: 4) {
                    if let city = photo.city {
                        Text(city)
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                    if let score = photo.score {
                        Spacer()
                        Text(String(format: "%.0f%%", score * 100))
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .onAppear {
            thumbnailLoader.load(from: photo.path)
        }
    }
}

/// Async thumbnail loader.
@MainActor
class ThumbnailLoader: ObservableObject {
    @Published var image: NSImage?

    private static let cache = NSCache<NSString, NSImage>()

    func load(from path: String) {
        // Check cache first
        if let cached = Self.cache.object(forKey: path as NSString) {
            self.image = cached
            return
        }

        // Load asynchronously
        Task.detached(priority: .background) {
            let url = URL(fileURLWithPath: path)
            guard let image = NSImage(contentsOf: url) else { return }

            // Create thumbnail
            let thumbnailSize = CGSize(width: 300, height: 300)
            let thumbnail = image.thumbnailImage(maxSize: thumbnailSize)

            await MainActor.run {
                Self.cache.setObject(thumbnail, forKey: path as NSString)
                self.image = thumbnail
            }
        }
    }
}

// MARK: - NSImage Extension

extension NSImage {
    func thumbnailImage(maxSize: CGSize) -> NSImage {
        let ratio = min(maxSize.width / size.width, maxSize.height / size.height)
        let newSize = CGSize(width: size.width * ratio, height: size.height * ratio)

        let thumbnail = NSImage(size: newSize)
        thumbnail.lockFocus()
        draw(in: NSRect(origin: .zero, size: newSize),
             from: NSRect(origin: .zero, size: size),
             operation: .copy,
             fraction: 1.0)
        thumbnail.unlockFocus()
        return thumbnail
    }
}

#Preview {
    PhotoGridView(photos: [
        SearchResult(id: "1", path: "/path/to/photo1.jpg", score: 0.95, description: "A beautiful sunset over the ocean", timestamp: nil, city: "Honolulu", state: "Hawaii", country: "USA"),
        SearchResult(id: "2", path: "/path/to/photo2.jpg", score: 0.85, description: "Mountain landscape", timestamp: nil, city: "Denver", state: "Colorado", country: "USA"),
    ])
    .frame(width: 600, height: 400)
}
