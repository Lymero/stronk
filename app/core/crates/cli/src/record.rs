//! `stronk-core record-champselect`: one champion select from the real client, in lcu-mock's
//! session format, scrubbed (stronk_lcu::scrub) and checked for identifiers before saving.

use std::collections::BTreeSet;
use std::path::Path;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use serde_json::{Value, json};
use stronk_lcu::{CHAMPION_SUMMARY, LcuClient, SESSION, scrub};
use stronk_service::ports::PortError;

pub struct Recording {
    pub steps: usize,
    pub champions: usize,
}

/// Polls the session until a champion select has started and ended (or `timeout`), keeping
/// each distinct scrubbed state as a step after an initial `lobby` step.
pub fn record(
    client: &LcuClient,
    out: &Path,
    timeout: Duration,
    poll: Duration,
) -> Result<Recording, String> {
    let started = Instant::now();
    let mut steps = vec![json!({"name": "lobby", "session": null})];
    let mut last: Option<Value> = None;
    let mut seen = false;
    while started.elapsed() < timeout {
        match client.get_json(SESSION).map_err(describe)? {
            None if seen => break, // champion select is over
            None => {}
            Some(raw) => {
                seen = true;
                let clean = scrub::session(&raw);
                if last.as_ref() != Some(&clean) {
                    let phase = clean
                        .pointer("/timer/phase")
                        .and_then(Value::as_str)
                        .unwrap_or("UNKNOWN");
                    steps.push(
                        json!({"name": format!("{} {}", phase, steps.len()), "session": clean}),
                    );
                    last = Some(clean);
                }
            }
        }
        std::thread::sleep(poll);
    }
    if !seen {
        return Err(format!("no champion select within {} s", timeout.as_secs()));
    }
    let champions = champions(client, &steps)?;
    let document = json!({
        "source": format!(
            "Recorded from the League client by `stronk-core record-champselect` on {}; kept fields \
             are an allowlist (app/core/crates/lcu/src/scrub.rs).",
            today()
        ),
        "champions": champions,
        "steps": steps,
    });
    let found = scrub::identifiers(&document);
    if !found.is_empty() {
        return Err(format!(
            "not saved: identifiers left at {}",
            found.join(", ")
        ));
    }
    if let Some(dir) = out.parent() {
        std::fs::create_dir_all(dir).map_err(|e| format!("{}: {e}", dir.display()))?;
    }
    let text = serde_json::to_string_pretty(&document).map_err(|e| e.to_string())?;
    std::fs::write(out, text + "\n").map_err(|e| format!("{}: {e}", out.display()))?;
    Ok(Recording {
        steps: steps.len(),
        champions: champions.len(),
    })
}

/// Champion ids/aliases/names for the champions the recording mentions (game data, not personal).
fn champions(client: &LcuClient, steps: &[Value]) -> Result<Vec<Value>, String> {
    let mut ids = BTreeSet::new();
    for step in steps {
        collect_ids(step, &mut ids);
    }
    let Some(Value::Array(summary)) = client.get_json(CHAMPION_SUMMARY).map_err(describe)? else {
        return Err("the client has no champion summary".into());
    };
    Ok(summary
        .iter()
        .filter(|c| {
            c.get("id")
                .and_then(Value::as_i64)
                .is_some_and(|id| ids.contains(&id))
        })
        .map(|c| json!({"id": c.get("id"), "alias": c.get("alias"), "name": c.get("name")}))
        .collect())
}

fn collect_ids(value: &Value, ids: &mut BTreeSet<i64>) {
    match value {
        Value::Object(map) => {
            for (key, child) in map {
                match (key.as_str(), child) {
                    ("championId" | "championPickIntent", Value::Number(n)) => {
                        ids.extend(n.as_i64().filter(|id| *id > 0));
                    }
                    ("myTeamBans" | "theirTeamBans", Value::Array(bans)) => {
                        ids.extend(bans.iter().filter_map(Value::as_i64).filter(|id| *id > 0));
                    }
                    _ => collect_ids(child, ids),
                }
            }
        }
        Value::Array(items) => items.iter().for_each(|item| collect_ids(item, ids)),
        _ => {}
    }
}

fn describe(e: PortError) -> String {
    e.to_string()
}

/// UTC date as YYYY-MM-DD (civil-from-days, no calendar crate needed).
fn today() -> String {
    let days = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_or(0, |d| d.as_secs() / 86_400);
    let z = i64::try_from(days).unwrap_or(0) + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z.rem_euclid(146_097);
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = doy - (153 * mp + 2) / 5 + 1;
    let month = if mp < 10 { mp + 3 } else { mp - 9 };
    let year = yoe + era * 400 + i64::from(month <= 2);
    format!("{year:04}-{month:02}-{day:02}")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn collects_every_mentioned_champion() {
        let step = json!({"session": {"myTeam": [{"championId": 64, "championPickIntent": 104}],
            "actions": [[{"championId": 222}]], "bans": {"myTeamBans": [7, -1], "theirTeamBans": []}}});
        let mut ids = BTreeSet::new();
        collect_ids(&step, &mut ids);
        assert_eq!(ids.into_iter().collect::<Vec<_>>(), [7, 64, 104, 222]);
    }

    #[test]
    fn dates_are_iso() {
        let date = today();
        assert_eq!(date.len(), 10);
        assert!(date.starts_with("20"));
    }
}
