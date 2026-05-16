import SwiftUI

/// Panel for filtering search results by date and location.
struct FilterPanel: View {
    @ObservedObject var viewModel: SearchViewModel
    @State private var isExpanded: Bool = false

    var body: some View {
        DisclosureGroup(isExpanded: $isExpanded) {
            VStack(alignment: .leading, spacing: 16) {
                // Date Range Filter
                dateRangeSection

                Divider()

                // Location Filter
                locationSection

                // Clear Filters Button
                if hasActiveFilters {
                    HStack {
                        Spacer()
                        Button("Clear Filters") {
                            clearFilters()
                        }
                        .buttonStyle(.link)
                    }
                }
            }
            .padding(.top, 8)
        } label: {
            HStack {
                Label("Filters", systemImage: "line.3.horizontal.decrease.circle")
                    .font(.headline)

                if hasActiveFilters {
                    Text("(\(activeFilterCount))")
                        .font(.caption)
                        .foregroundColor(.blue)
                }
            }
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
    }

    // MARK: - Date Range Section

    private var dateRangeSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Date Range")
                .font(.subheadline)
                .foregroundColor(.secondary)

            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("From")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    DatePicker(
                        "",
                        selection: Binding(
                            get: { viewModel.startDate ?? Date.distantPast },
                            set: { viewModel.startDate = $0 }
                        ),
                        displayedComponents: .date
                    )
                    .labelsHidden()
                    .datePickerStyle(.field)
                }

                VStack(alignment: .leading, spacing: 4) {
                    Text("To")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    DatePicker(
                        "",
                        selection: Binding(
                            get: { viewModel.endDate ?? Date() },
                            set: { viewModel.endDate = $0 }
                        ),
                        displayedComponents: .date
                    )
                    .labelsHidden()
                    .datePickerStyle(.field)
                }

                if viewModel.startDate != nil || viewModel.endDate != nil {
                    Button {
                        viewModel.startDate = nil
                        viewModel.endDate = nil
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundColor(.secondary)
                    }
                    .buttonStyle(.plain)
                    .help("Clear date filter")
                }
            }

            // Quick date presets
            HStack(spacing: 8) {
                ForEach(DatePreset.allCases, id: \.self) { preset in
                    Button(preset.title) {
                        applyDatePreset(preset)
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                }
            }
        }
    }

    // MARK: - Location Section

    private var locationSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Location")
                .font(.subheadline)
                .foregroundColor(.secondary)

            HStack {
                TextField("City, state, or country", text: Binding(
                    get: { viewModel.locationFilter ?? "" },
                    set: { viewModel.locationFilter = $0.isEmpty ? nil : $0 }
                ))
                .textFieldStyle(.roundedBorder)

                if viewModel.locationFilter != nil {
                    Button {
                        viewModel.locationFilter = nil
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundColor(.secondary)
                    }
                    .buttonStyle(.plain)
                    .help("Clear location filter")
                }
            }

            if let resolved = viewModel.locationResolved {
                HStack(spacing: 4) {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundColor(.green)
                        .font(.caption)
                    Text("Resolved: \(resolved.query)")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
        }
    }

    // MARK: - Helpers

    private var hasActiveFilters: Bool {
        viewModel.startDate != nil ||
        viewModel.endDate != nil ||
        viewModel.locationFilter != nil
    }

    private var activeFilterCount: Int {
        var count = 0
        if viewModel.startDate != nil || viewModel.endDate != nil { count += 1 }
        if viewModel.locationFilter != nil { count += 1 }
        return count
    }

    private func clearFilters() {
        viewModel.clearFilters()
    }

    private func applyDatePreset(_ preset: DatePreset) {
        let calendar = Calendar.current
        let now = Date()

        switch preset {
        case .today:
            viewModel.startDate = calendar.startOfDay(for: now)
            viewModel.endDate = now
        case .thisWeek:
            let weekStart = calendar.date(from: calendar.dateComponents([.yearForWeekOfYear, .weekOfYear], from: now))
            viewModel.startDate = weekStart
            viewModel.endDate = now
        case .thisMonth:
            let monthStart = calendar.date(from: calendar.dateComponents([.year, .month], from: now))
            viewModel.startDate = monthStart
            viewModel.endDate = now
        case .thisYear:
            let yearStart = calendar.date(from: calendar.dateComponents([.year], from: now))
            viewModel.startDate = yearStart
            viewModel.endDate = now
        }
    }
}

// MARK: - Date Preset

enum DatePreset: String, CaseIterable {
    case today = "Today"
    case thisWeek = "This Week"
    case thisMonth = "This Month"
    case thisYear = "This Year"

    var title: String { rawValue }
}

// MARK: - Preview

#Preview {
    FilterPanel(viewModel: SearchViewModel())
        .frame(width: 400)
        .padding()
}
