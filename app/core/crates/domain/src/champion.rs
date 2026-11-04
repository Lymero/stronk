//! Champion keys. Builds are published under each champion's Data Dragon id, the name Riot's
//! match data uses ("Fiddlesticks"); the client names champions by their alias in
//! `champion-summary.json`, which is the same but for Fiddlesticks ("FiddleSticks").

/// Client aliases that differ from the Data Dragon id builds are published under.
const DATA_KEYS: [(&str, &str); 1] = [("FiddleSticks", "Fiddlesticks")];

/// The key builds are published under for the client's `alias`.
pub fn data_key(alias: &str) -> &str {
    DATA_KEYS
        .iter()
        .find(|(client, _)| *client == alias)
        .map_or(alias, |(_, data)| data)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_client_alias_maps_to_the_data_key() {
        assert_eq!(data_key("FiddleSticks"), "Fiddlesticks");
        assert_eq!(data_key("LeeSin"), "LeeSin");
        assert_eq!(data_key("MonkeyKing"), "MonkeyKing");
    }
}
