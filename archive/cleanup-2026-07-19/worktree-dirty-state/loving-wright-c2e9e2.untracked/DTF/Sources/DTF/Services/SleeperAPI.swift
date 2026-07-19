import Foundation

/// Public Sleeper REST API (no auth). Used to pull a league's roster + user
/// list so we can hand them to our backend's `/api/session/init`.
///
/// Docs: https://docs.sleeper.com/
enum SleeperAPI {
    static let base = URL(string: "https://api.sleeper.app/v1")!

    struct Roster: Decodable, Hashable {
        let rosterID: Int
        let ownerID: String?
        let coOwners: [String]?
        let players: [String]?

        enum CodingKeys: String, CodingKey {
            case rosterID = "roster_id"
            case ownerID = "owner_id"
            case coOwners = "co_owners"
            case players
        }
    }

    struct User: Decodable, Hashable {
        let userID: String
        let username: String?
        let displayName: String?
        let avatar: String?

        enum CodingKeys: String, CodingKey {
            case userID = "user_id"
            case username
            case displayName = "display_name"
            case avatar
        }
    }

    static func rosters(leagueID: String) async throws -> [Roster] {
        let url = base.appendingPathComponent("league/\(leagueID)/rosters")
        let (data, _) = try await URLSession.shared.data(from: url)
        return try JSONDecoder().decode([Roster].self, from: data)
    }

    static func users(leagueID: String) async throws -> [User] {
        let url = base.appendingPathComponent("league/\(leagueID)/users")
        let (data, _) = try await URLSession.shared.data(from: url)
        return try JSONDecoder().decode([User].self, from: data)
    }
}
