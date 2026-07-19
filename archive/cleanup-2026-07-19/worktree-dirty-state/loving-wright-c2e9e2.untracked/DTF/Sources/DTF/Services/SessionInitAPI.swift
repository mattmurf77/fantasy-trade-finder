import Foundation

/// Wrapper for `POST /api/session/init` — hands the backend the league roster
/// context required by every `/api/trades/*` and `/api/league/*` endpoint.
///
/// Extension-auth alone gives us a session token but no `sess["league"]`;
/// that key is populated here.
enum SessionInitAPI {
    struct OpponentRoster: Encodable {
        let userID: String
        let username: String
        let playerIDs: [String]

        enum CodingKeys: String, CodingKey {
            case userID = "user_id"
            case username
            case playerIDs = "player_ids"
        }
    }

    struct InitBody: Encodable {
        let userID: String
        let leagueID: String
        let leagueName: String
        let userPlayerIDs: [String]
        let opponentRosters: [OpponentRoster]
        let displayName: String
        let username: String
        let avatar: String?

        enum CodingKeys: String, CodingKey {
            case userID = "user_id"
            case leagueID = "league_id"
            case leagueName = "league_name"
            case userPlayerIDs = "user_player_ids"
            case opponentRosters = "opponent_rosters"
            case displayName = "display_name"
            case username
            case avatar
        }
    }

    /// Response shape is loose — we only care that it returned 2xx.
    struct InitAck: Decodable {
        init() {}
        init(from decoder: Decoder) throws {
            _ = try? decoder.singleValueContainer()
        }
    }

    @discardableResult
    static func initSession(_ body: InitBody) async throws -> InitAck {
        try await APIClient.shared.post("/api/session/init", body: body, as: InitAck.self)
    }

    /// Convenience: fetch Sleeper rosters + users for `league`, build the
    /// `InitBody`, and POST it. Caller must provide the current user's
    /// sleeper user_id + profile info.
    static func performFullInit(
        userID: String,
        username: String,
        displayName: String,
        avatar: String?,
        league: LeagueSummary
    ) async throws {
        async let rostersT = SleeperAPI.rosters(leagueID: league.leagueID)
        async let usersT = SleeperAPI.users(leagueID: league.leagueID)
        let rosters = try await rostersT
        let users = try await usersT

        let userByID = Dictionary(uniqueKeysWithValues: users.map { ($0.userID, $0) })

        var userPlayerIDs: [String] = []
        var opponents: [OpponentRoster] = []
        for r in rosters {
            let owner = r.ownerID ?? r.coOwners?.first ?? ""
            let players = r.players ?? []
            if owner == userID {
                userPlayerIDs = players
            } else {
                let name = userByID[owner]?.username
                    ?? userByID[owner]?.displayName
                    ?? "user_\(owner.prefix(6))"
                opponents.append(OpponentRoster(
                    userID: owner,
                    username: name,
                    playerIDs: players
                ))
            }
        }

        let body = InitBody(
            userID: userID,
            leagueID: league.leagueID,
            leagueName: league.name,
            userPlayerIDs: userPlayerIDs,
            opponentRosters: opponents,
            displayName: displayName,
            username: username,
            avatar: avatar
        )
        _ = try await initSession(body)
    }
}
