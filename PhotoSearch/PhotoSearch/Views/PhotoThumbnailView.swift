import SwiftUI

/// Individual photo thumbnail view with info overlay.
struct PhotoThumbnailView: View {
    let photo: SearchResult
    let isSelected: Bool
    var onSelect: (() -> Void)?
    var onDoubleClick: (() -> Void)?

    @StateObject private var thumbnailLoader = ThumbnailLoader()
    @State private var isHovering = false

    var body: some View {
        VStack(spacing: 4) {
            // Thumbnail image
            thumbnailView
                .cornerRadius(8)
                .overlay(selectionOverlay)
                .shadow(color: .black.opacity(isHovering ? 0.2 : 0.1), radius: isHovering ? 4 : 2, x: 0, y: 1)
                .scaleEffect(isHovering ? 1.02 : 1.0)
                .animation(.easeInOut(duration: 0.15), value: isHovering)

            // Photo info
            photoInfoView
        }
        .onHover { hovering in
            isHovering = hovering
        }
        .onTapGesture(count: 2) {
            onDoubleClick?()
        }
        .onTapGesture {
            onSelect?()
        }
        .onAppear {
            thumbnailLoader.load(from: photo.path)
        }
        .onDisappear {
            thumbnailLoader.cancel()
        }
    }

    // MARK: - Subviews

    private var thumbnailView: some View {
        ZStack {
            // Background placeholder
            Rectangle()
                .fill(Color(nsColor: .separatorColor))
                .aspectRatio(1, contentMode: .fit)

            // Thumbnail image
            if let image = thumbnailLoader.image {
                Image(nsImage: image)
                    .resizable()
                    .aspectRatio(contentMode: .fill)
                    .frame(minWidth: 0, maxWidth: .infinity, minHeight: 0, maxHeight: .infinity)
                    .clipped()
            } else if thumbnailLoader.isLoading {
                ProgressView()
                    .scaleEffect(0.8)
            } else {
                // Error or missing image
                Image(systemName: "photo")
                    .font(.largeTitle)
                    .foregroundColor(.secondary)
            }

            // Score badge
            if let score = photo.score, score > 0 {
                VStack {
                    HStack {
                        Spacer()
                        scoreBadge(score: score)
                            .padding(6)
                    }
                    Spacer()
                }
            }
        }
    }

    private var selectionOverlay: some View {
        RoundedRectangle(cornerRadius: 8)
            .stroke(isSelected ? Color.accentColor : Color.clear, lineWidth: 3)
    }

    private var photoInfoView: some View {
        VStack(alignment: .leading, spacing: 2) {
            // Description
            if let description = photo.description, !description.isEmpty {
                Text(description)
                    .font(.caption)
                    .lineLimit(2)
                    .foregroundColor(.primary)
                    .help(description)
            }

            // Location and metadata
            HStack(spacing: 4) {
                if let location = locationText {
                    HStack(spacing: 2) {
                        Image(systemName: "location.fill")
                            .font(.system(size: 8))
                        Text(location)
                    }
                    .font(.caption2)
                    .foregroundColor(.secondary)
                }

                Spacer()

                if let timestamp = photo.timestamp {
                    Text(timestamp, style: .date)
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func scoreBadge(score: Double) -> some View {
        Text(String(format: "%.0f%%", score * 100))
            .font(.caption2)
            .fontWeight(.medium)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(scoreColor(for: score).opacity(0.9))
            .foregroundColor(.white)
            .cornerRadius(4)
    }

    // MARK: - Helpers

    private var locationText: String? {
        [photo.city, photo.state, photo.country]
            .compactMap { $0 }
            .first
    }

    private func scoreColor(for score: Double) -> Color {
        switch score {
        case 0.9...: return .green
        case 0.7..<0.9: return .blue
        case 0.5..<0.7: return .orange
        default: return .gray
        }
    }
}

// MARK: - Preview

#Preview("Selected") {
    PhotoThumbnailView(
        photo: SearchResult(
            id: "1",
            path: "/path/to/photo.jpg",
            score: 0.95,
            description: "A beautiful sunset over the ocean with orange and pink clouds",
            timestamp: Date(),
            city: "Honolulu",
            state: "Hawaii",
            country: "USA"
        ),
        isSelected: true
    )
    .frame(width: 200)
    .padding()
}

#Preview("Not Selected") {
    PhotoThumbnailView(
        photo: SearchResult(
            id: "2",
            path: "/path/to/photo.jpg",
            score: 0.72,
            description: "Mountain landscape",
            timestamp: nil,
            city: "Denver",
            state: nil,
            country: "USA"
        ),
        isSelected: false
    )
    .frame(width: 200)
    .padding()
}
