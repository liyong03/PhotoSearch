import SwiftUI

/// Search bar component with icon, clear button, and filter indicators.
struct SearchBar: View {
    @Binding var text: String
    var placeholder: String = "Search photos..."
    var onSubmit: (() -> Void)?
    var onClear: (() -> Void)?

    /// Active filters to display as badges
    var activeFilters: [SearchFilter] = []

    @FocusState private var isFocused: Bool
    @State private var isHovering = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Main search bar
            HStack(spacing: 8) {
                // Search icon
                Image(systemName: "magnifyingglass")
                    .foregroundColor(isFocused ? .accentColor : .secondary)
                    .animation(.easeInOut(duration: 0.15), value: isFocused)

                // Text field
                TextField(placeholder, text: $text)
                    .textFieldStyle(.plain)
                    .focused($isFocused)
                    .onSubmit {
                        onSubmit?()
                    }

                // Clear button
                if !text.isEmpty {
                    Button {
                        text = ""
                        onClear?()
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundColor(.secondary)
                    }
                    .buttonStyle(.plain)
                    .transition(.scale.combined(with: .opacity))
                }

                // Search button (for explicit search)
                if !text.isEmpty {
                    Button {
                        onSubmit?()
                    } label: {
                        Image(systemName: "arrow.right.circle.fill")
                            .foregroundColor(.accentColor)
                    }
                    .buttonStyle(.plain)
                    .transition(.scale.combined(with: .opacity))
                }
            }
            .padding(10)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(Color(nsColor: .controlBackgroundColor))
                    .overlay(
                        RoundedRectangle(cornerRadius: 8)
                            .stroke(isFocused ? Color.accentColor.opacity(0.5) : Color.clear, lineWidth: 2)
                    )
            )
            .animation(.easeInOut(duration: 0.15), value: text.isEmpty)

            // Active filters
            if !activeFilters.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        ForEach(activeFilters) { filter in
                            FilterBadge(filter: filter)
                        }
                    }
                }
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: .focusSearch)) { _ in
            isFocused = true
        }
    }
}

// MARK: - Search Filter

/// Represents an active search filter.
struct SearchFilter: Identifiable, Equatable {
    let id = UUID()
    let type: FilterType
    let value: String
    var onRemove: (() -> Void)?

    enum FilterType: String {
        case location = "Location"
        case dateRange = "Date"
        case tag = "Tag"

        var icon: String {
            switch self {
            case .location: return "location.fill"
            case .dateRange: return "calendar"
            case .tag: return "tag.fill"
            }
        }

        var color: Color {
            switch self {
            case .location: return .blue
            case .dateRange: return .orange
            case .tag: return .green
            }
        }
    }

    static func == (lhs: SearchFilter, rhs: SearchFilter) -> Bool {
        lhs.id == rhs.id
    }
}

// MARK: - Filter Badge

/// Badge displaying an active filter with remove button.
struct FilterBadge: View {
    let filter: SearchFilter

    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: filter.type.icon)
                .font(.caption2)

            Text(filter.value)
                .font(.caption)
                .lineLimit(1)

            if filter.onRemove != nil {
                Button {
                    filter.onRemove?()
                } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 8, weight: .bold))
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(filter.type.color.opacity(0.15))
        .foregroundColor(filter.type.color)
        .cornerRadius(12)
    }
}

// MARK: - Search Suggestions

/// View showing search suggestions.
struct SearchSuggestionsView: View {
    let suggestions: [String]
    var onSelect: ((String) -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            ForEach(suggestions, id: \.self) { suggestion in
                Button {
                    onSelect?(suggestion)
                } label: {
                    HStack {
                        Image(systemName: "magnifyingglass")
                            .foregroundColor(.secondary)
                        Text(suggestion)
                            .foregroundColor(.primary)
                        Spacer()
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)

                if suggestion != suggestions.last {
                    Divider()
                        .padding(.leading, 36)
                }
            }
        }
        .background(Color(nsColor: .controlBackgroundColor))
        .cornerRadius(8)
        .shadow(color: .black.opacity(0.1), radius: 4, x: 0, y: 2)
    }
}

// MARK: - Preview

#Preview("Empty") {
    VStack {
        SearchBar(text: .constant(""))
        Spacer()
    }
    .padding()
    .frame(width: 400, height: 200)
}

#Preview("With Text") {
    VStack {
        SearchBar(text: .constant("sunset beach"))
        Spacer()
    }
    .padding()
    .frame(width: 400, height: 200)
}

#Preview("With Filters") {
    VStack {
        SearchBar(
            text: .constant("sunset"),
            activeFilters: [
                SearchFilter(type: .location, value: "Hawaii"),
                SearchFilter(type: .dateRange, value: "2024")
            ]
        )
        Spacer()
    }
    .padding()
    .frame(width: 400, height: 200)
}

#Preview("Suggestions") {
    SearchSuggestionsView(suggestions: [
        "sunset beach",
        "sunset mountains",
        "sunset from Hawaii"
    ])
    .padding()
    .frame(width: 300)
}
