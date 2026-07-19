import SwiftUI

/// Shown between "league selected" and "MainTabView" while `/api/session/init`
/// pulls Sleeper rosters and seeds the backend session. Also handles failure
/// + retry.
struct LeagueInitGate: View {
    @EnvironmentObject private var session: SessionService

    var body: some View {
        ZStack {
            Color.DTF.background.ignoresSafeArea()
            VStack(spacing: 20) {
                switch session.leagueInitPhase {
                case .idle, .loading:
                    loadingBlock
                case .ready:
                    // RootRouter should route past us immediately — render
                    // nothing visible during the transition.
                    EmptyView()
                case .failed(let msg):
                    failureBlock(msg)
                }
            }
            .padding(32)
        }
        .task {
            await session.performSessionInit()
        }
    }

    private var loadingBlock: some View {
        VStack(spacing: 16) {
            ProgressView()
                #if os(iOS)
                .tint(Color.DTF.accent)
                .scaleEffect(1.4)
                #else
                .controlSize(.large)
                #endif
                .padding(.bottom, 8)
            Text("Setting up \(session.selectedLeagueName ?? "your league")")
                .font(.system(size: 17, weight: .semibold, design: .rounded))
                .foregroundStyle(Color.DTF.textPrimary)
            Text("Pulling rosters from Sleeper and priming the trade engine.")
                .font(.system(size: 13))
                .foregroundStyle(Color.DTF.textMuted)
                .multilineTextAlignment(.center)
        }
    }

    private func failureBlock(_ msg: String) -> some View {
        VStack(spacing: 14) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 36))
                .foregroundStyle(Color.DTF.warning)
            Text("Couldn't set up the league")
                .font(.system(size: 17, weight: .semibold, design: .rounded))
                .foregroundStyle(Color.DTF.textPrimary)
            Text(msg)
                .font(.system(size: 13))
                .foregroundStyle(Color.DTF.textMuted)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 8)
            HStack(spacing: 10) {
                Button {
                    Task {
                        session.invalidateLeagueInit()
                        await session.performSessionInit()
                    }
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: "arrow.clockwise")
                        Text("Try again")
                    }
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(Color.DTF.accent)
                    .padding(.horizontal, 18)
                    .padding(.vertical, 10)
                    .background(Capsule().fill(Color.DTF.accentDim))
                }
                .buttonStyle(.plain)
                Button {
                    session.clearSelectedLeague()
                } label: {
                    Text("Pick a different league")
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(Color.DTF.textMuted)
                }
                .buttonStyle(.plain)
            }
            .padding(.top, 4)
        }
    }
}
