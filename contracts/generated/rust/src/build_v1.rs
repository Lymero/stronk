#![allow(clippy::redundant_closure_call)]
#![allow(clippy::needless_lifetimes)]
#![allow(clippy::match_single_binding)]
#![allow(clippy::clone_on_copy)]

#[doc = "Build statistics for one champion and role, published at /{patch}/{region}/{elo}/{champion}/{role}.json."]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct Build {
    #[doc = "Data Dragon champion key (for example \"Viego\")."]
    pub champion: BuildChampion,
    #[doc = "Elo bracket id (for example \"diamond_plus\")."]
    pub elo: BuildElo,
    #[doc = "Games behind this file."]
    pub games: u64,
    pub items: ::std::vec::Vec<ItemOption>,
    #[doc = "The item slot of the late items: the item completed at this slot and every later one, as one decision (ADR-067). Absent: every slot is its own."]
    #[serde(
        rename = "lateSlot",
        skip_serializing_if = "::std::option::Option::is_none"
    )]
    pub late_slot: ::std::option::Option<::std::num::NonZeroU64>,
    pub patch: Patch,
    #[doc = "Riot platform or region id, lower case (for example \"euw1\")."]
    pub region: BuildRegion,
    pub role: Role,
    #[doc = "Each rune row on its own, for information: every primary row, the secondary pair and every stat shard row (ADR-057). Imports still write a whole page from `runes`."]
    #[serde(
        rename = "runeChoices",
        default,
        skip_serializing_if = "::std::vec::Vec::is_empty"
    )]
    pub rune_choices: ::std::vec::Vec<RuneChoice>,
    pub runes: ::std::vec::Vec<RuneOption>,
    #[doc = "Contract major version. A breaking change publishes a new version alongside this one."]
    #[serde(rename = "schemaVersion")]
    pub schema_version: BuildSchemaVersion,
    #[serde(
        rename = "skillOrder",
        default,
        skip_serializing_if = "::std::vec::Vec::is_empty"
    )]
    pub skill_order: ::std::vec::Vec<SkillOrderOption>,
    pub spells: ::std::vec::Vec<SpellOption>,
    #[doc = "The starting items (ADR-071): what players buy before leaving base, without potions and wards, each start estimated among the others."]
    #[serde(default, skip_serializing_if = "::std::vec::Vec::is_empty")]
    pub starts: ::std::vec::Vec<StartOption>,
}
#[doc = "Data Dragon champion key (for example \"Viego\")."]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct BuildChampion(::std::string::String);
impl ::std::ops::Deref for BuildChampion {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<BuildChampion> for ::std::string::String {
    fn from(value: BuildChampion) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for BuildChampion {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        static PATTERN: ::std::sync::LazyLock<::regress::Regex> =
            ::std::sync::LazyLock::new(|| ::regress::Regex::new("^[A-Za-z0-9]{1,32}$").unwrap());
        if PATTERN.find(value).is_none() {
            return Err("doesn't match pattern \"^[A-Za-z0-9]{1,32}$\"".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for BuildChampion {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for BuildChampion {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for BuildChampion {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "Elo bracket id (for example \"diamond_plus\")."]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct BuildElo(::std::string::String);
impl ::std::ops::Deref for BuildElo {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<BuildElo> for ::std::string::String {
    fn from(value: BuildElo) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for BuildElo {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        static PATTERN: ::std::sync::LazyLock<::regress::Regex> =
            ::std::sync::LazyLock::new(|| ::regress::Regex::new("^[a-z_]{2,32}$").unwrap());
        if PATTERN.find(value).is_none() {
            return Err("doesn't match pattern \"^[a-z_]{2,32}$\"".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for BuildElo {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for BuildElo {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for BuildElo {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "Riot platform or region id, lower case (for example \"euw1\")."]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct BuildRegion(::std::string::String);
impl ::std::ops::Deref for BuildRegion {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<BuildRegion> for ::std::string::String {
    fn from(value: BuildRegion) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for BuildRegion {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        static PATTERN: ::std::sync::LazyLock<::regress::Regex> =
            ::std::sync::LazyLock::new(|| ::regress::Regex::new("^[a-z0-9]{2,8}$").unwrap());
        if PATTERN.find(value).is_none() {
            return Err("doesn't match pattern \"^[a-z0-9]{2,8}$\"".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for BuildRegion {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for BuildRegion {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for BuildRegion {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "Contract major version. A breaking change publishes a new version alongside this one."]
#[derive(:: serde :: Serialize, Clone, Debug)]
#[serde(transparent)]
pub struct BuildSchemaVersion(i64);
impl ::std::ops::Deref for BuildSchemaVersion {
    type Target = i64;
    fn deref(&self) -> &i64 {
        &self.0
    }
}
impl ::std::convert::From<BuildSchemaVersion> for i64 {
    fn from(value: BuildSchemaVersion) -> Self {
        value.0
    }
}
impl ::std::convert::TryFrom<i64> for BuildSchemaVersion {
    type Error = self::error::ConversionError;
    fn try_from(value: i64) -> ::std::result::Result<Self, self::error::ConversionError> {
        if ![1_i64].contains(&value) {
            Err("invalid value".into())
        } else {
            Ok(Self(value))
        }
    }
}
impl<'de> ::serde::Deserialize<'de> for BuildSchemaVersion {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        Self::try_from(<i64>::deserialize(deserializer)?)
            .map_err(|e| <D::Error as ::serde::de::Error>::custom(e.to_string()))
    }
}
#[doc = "The option head to head with the most played option at its decision point (docs/wpa-method.md, section 5; ADR-036)."]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct Comparison {
    #[doc = "95% interval of `wpa`."]
    #[serde(skip_serializing_if = "::std::option::Option::is_none")]
    pub ci: ::std::option::Option<Interval>,
    #[doc = "False-discovery-adjusted p-value of no difference, across the patch."]
    pub q: f64,
    #[doc = "The most played option compared with: keystone id for runes, item id for items."]
    pub versus: u64,
    #[doc = "Win probability added by this option against `versus`."]
    pub wpa: f64,
}
#[doc = "Why an estimate should not be trusted at face value. See docs/wpa-method.md, section 7."]
#[derive(
    :: serde :: Deserialize,
    :: serde :: Serialize,
    Clone,
    Copy,
    Debug,
    Eq,
    Hash,
    Ord,
    PartialEq,
    PartialOrd,
)]
pub enum Flag {
    #[serde(rename = "low_sample")]
    LowSample,
    #[serde(rename = "low_overlap")]
    LowOverlap,
    #[serde(rename = "no_clear_difference")]
    NoClearDifference,
    #[serde(rename = "fragile")]
    Fragile,
}
impl ::std::fmt::Display for Flag {
    fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> ::std::fmt::Result {
        match *self {
            Self::LowSample => f.write_str("low_sample"),
            Self::LowOverlap => f.write_str("low_overlap"),
            Self::NoClearDifference => f.write_str("no_clear_difference"),
            Self::Fragile => f.write_str("fragile"),
        }
    }
}
impl ::std::str::FromStr for Flag {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        match value {
            "low_sample" => Ok(Self::LowSample),
            "low_overlap" => Ok(Self::LowOverlap),
            "no_clear_difference" => Ok(Self::NoClearDifference),
            "fragile" => Ok(Self::Fragile),
            _ => Err("invalid value".into()),
        }
    }
}
impl ::std::convert::TryFrom<&str> for Flag {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for Flag {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
#[doc = "95% interval [low, high] of the WPA estimate."]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(transparent)]
pub struct Interval(pub [f64; 2usize]);
impl ::std::ops::Deref for Interval {
    type Target = [f64; 2usize];
    fn deref(&self) -> &[f64; 2usize] {
        &self.0
    }
}
impl ::std::convert::From<Interval> for [f64; 2usize] {
    fn from(value: Interval) -> Self {
        value.0
    }
}
impl ::std::convert::From<[f64; 2usize]> for Interval {
    fn from(value: [f64; 2usize]) -> Self {
        Self(value)
    }
}
#[doc = "`ItemOption`"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct ItemOption {
    #[serde(deserialize_with = "::std::option::Option::deserialize")]
    pub ci: ::std::option::Option<Interval>,
    #[serde(skip_serializing_if = "::std::option::Option::is_none")]
    pub comparison: ::std::option::Option<Comparison>,
    pub flags: ::std::vec::Vec<Flag>,
    #[doc = "Data Dragon item id."]
    pub item: ::std::num::NonZeroU64,
    pub n: u64,
    #[doc = "Times this item was chosen at this slot."]
    #[serde(skip_serializing_if = "::std::option::Option::is_none")]
    pub picks: ::std::option::Option<u64>,
    pub slot: ::std::num::NonZeroU64,
    #[serde(deserialize_with = "::std::option::Option::deserialize")]
    pub wpa: ::std::option::Option<f64>,
}
#[doc = "Game patch, major.minor (for example \"26.20\")."]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct Patch(::std::string::String);
impl ::std::ops::Deref for Patch {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<Patch> for ::std::string::String {
    fn from(value: Patch) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for Patch {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        static PATTERN: ::std::sync::LazyLock<::regress::Regex> =
            ::std::sync::LazyLock::new(|| {
                ::regress::Regex::new("^[0-9]{1,3}\\.[0-9]{1,3}$").unwrap()
            });
        if PATTERN.find(value).is_none() {
            return Err("doesn't match pattern \"^[0-9]{1,3}\\.[0-9]{1,3}$\"".into());
        }
        Ok(Self(value.to_string()))
    }
}
impl ::std::convert::TryFrom<&str> for Patch {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for Patch {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for Patch {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        ::std::string::String::deserialize(deserializer)?
            .parse()
            .map_err(|e: self::error::ConversionError| {
                <D::Error as ::serde::de::Error>::custom(e.to_string())
            })
    }
}
#[doc = "`Role`"]
#[derive(
    :: serde :: Deserialize,
    :: serde :: Serialize,
    Clone,
    Copy,
    Debug,
    Eq,
    Hash,
    Ord,
    PartialEq,
    PartialOrd,
)]
pub enum Role {
    #[serde(rename = "TOP")]
    Top,
    #[serde(rename = "JUNGLE")]
    Jungle,
    #[serde(rename = "MIDDLE")]
    Middle,
    #[serde(rename = "BOTTOM")]
    Bottom,
    #[serde(rename = "UTILITY")]
    Utility,
}
impl ::std::fmt::Display for Role {
    fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> ::std::fmt::Result {
        match *self {
            Self::Top => f.write_str("TOP"),
            Self::Jungle => f.write_str("JUNGLE"),
            Self::Middle => f.write_str("MIDDLE"),
            Self::Bottom => f.write_str("BOTTOM"),
            Self::Utility => f.write_str("UTILITY"),
        }
    }
}
impl ::std::str::FromStr for Role {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        match value {
            "TOP" => Ok(Self::Top),
            "JUNGLE" => Ok(Self::Jungle),
            "MIDDLE" => Ok(Self::Middle),
            "BOTTOM" => Ok(Self::Bottom),
            "UTILITY" => Ok(Self::Utility),
            _ => Err("invalid value".into()),
        }
    }
}
impl ::std::convert::TryFrom<&str> for Role {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for Role {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
#[doc = "One choice of one rune row, estimated among the choices of that row."]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct RuneChoice {
    #[serde(deserialize_with = "::std::option::Option::deserialize")]
    pub ci: ::std::option::Option<Interval>,
    #[serde(skip_serializing_if = "::std::option::Option::is_none")]
    pub comparison: ::std::option::Option<RuneChoiceComparison>,
    pub flags: ::std::vec::Vec<Flag>,
    #[doc = "Games with this choice."]
    #[serde(skip_serializing_if = "::std::option::Option::is_none")]
    pub games: ::std::option::Option<u64>,
    #[doc = "A primary tree's row, the secondary tree's two runes, or a stat shard row."]
    pub kind: RuneChoiceKind,
    #[doc = "Decisions behind the estimate."]
    pub n: u64,
    #[doc = "The rune or shard chosen, or the secondary pair, smallest id first."]
    pub perks: ::std::vec::Vec<u64>,
    #[doc = "The row, for primary rows (after the keystone) and shard rows."]
    #[serde(skip_serializing_if = "::std::option::Option::is_none")]
    pub row: ::std::option::Option<::std::num::NonZeroU64>,
    #[doc = "The tree, for primary rows and secondary pairs."]
    #[serde(skip_serializing_if = "::std::option::Option::is_none")]
    pub style: ::std::option::Option<u64>,
    #[doc = "Win probability added against the row's other choices; null when not estimated."]
    #[serde(deserialize_with = "::std::option::Option::deserialize")]
    pub wpa: ::std::option::Option<f64>,
}
#[doc = "The choice head to head with its row's most played choice (ADR-036)."]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct RuneChoiceComparison {
    #[doc = "95% interval of `wpa`."]
    #[serde(skip_serializing_if = "::std::option::Option::is_none")]
    pub ci: ::std::option::Option<Interval>,
    #[doc = "False-discovery-adjusted p-value of no difference, across the patch."]
    pub q: f64,
    #[doc = "The row's most played choice: one rune or shard, or the secondary pair."]
    pub versus: ::std::vec::Vec<u64>,
    #[doc = "Win probability added by this choice against `versus`."]
    pub wpa: f64,
}
#[doc = "A primary tree's row, the secondary tree's two runes, or a stat shard row."]
#[derive(
    :: serde :: Deserialize,
    :: serde :: Serialize,
    Clone,
    Copy,
    Debug,
    Eq,
    Hash,
    Ord,
    PartialEq,
    PartialOrd,
)]
pub enum RuneChoiceKind {
    #[serde(rename = "primary")]
    Primary,
    #[serde(rename = "secondary")]
    Secondary,
    #[serde(rename = "shard")]
    Shard,
}
impl ::std::fmt::Display for RuneChoiceKind {
    fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> ::std::fmt::Result {
        match *self {
            Self::Primary => f.write_str("primary"),
            Self::Secondary => f.write_str("secondary"),
            Self::Shard => f.write_str("shard"),
        }
    }
}
impl ::std::str::FromStr for RuneChoiceKind {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        match value {
            "primary" => Ok(Self::Primary),
            "secondary" => Ok(Self::Secondary),
            "shard" => Ok(Self::Shard),
            _ => Err("invalid value".into()),
        }
    }
}
impl ::std::convert::TryFrom<&str> for RuneChoiceKind {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for RuneChoiceKind {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
#[doc = "`RuneOption`"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct RuneOption {
    #[serde(deserialize_with = "::std::option::Option::deserialize")]
    pub ci: ::std::option::Option<Interval>,
    #[serde(skip_serializing_if = "::std::option::Option::is_none")]
    pub comparison: ::std::option::Option<Comparison>,
    pub flags: ::std::vec::Vec<Flag>,
    #[doc = "Games played with exactly this full page."]
    #[serde(skip_serializing_if = "::std::option::Option::is_none")]
    pub games: ::std::option::Option<u64>,
    #[doc = "Decisions behind the estimate."]
    pub n: u64,
    pub page: RunePage,
    #[doc = "Win probability added; null when flagged low_overlap."]
    #[serde(deserialize_with = "::std::option::Option::deserialize")]
    pub wpa: ::std::option::Option<f64>,
}
#[doc = "`RunePage`"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct RunePage {
    #[doc = "Four primary, two secondary, three shards."]
    pub perks: [u64; 9usize],
    #[serde(rename = "primaryStyle")]
    pub primary_style: u64,
    #[serde(rename = "subStyle")]
    pub sub_style: u64,
}
#[doc = "`SkillOrderOption`"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct SkillOrderOption {
    pub n: u64,
    pub order: ::std::vec::Vec<SkillOrderOptionOrderItem>,
}
#[doc = "`SkillOrderOptionOrderItem`"]
#[derive(
    :: serde :: Deserialize,
    :: serde :: Serialize,
    Clone,
    Copy,
    Debug,
    Eq,
    Hash,
    Ord,
    PartialEq,
    PartialOrd,
)]
pub enum SkillOrderOptionOrderItem {
    Q,
    W,
    E,
    R,
}
impl ::std::fmt::Display for SkillOrderOptionOrderItem {
    fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> ::std::fmt::Result {
        match *self {
            Self::Q => f.write_str("Q"),
            Self::W => f.write_str("W"),
            Self::E => f.write_str("E"),
            Self::R => f.write_str("R"),
        }
    }
}
impl ::std::str::FromStr for SkillOrderOptionOrderItem {
    type Err = self::error::ConversionError;
    fn from_str(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        match value {
            "Q" => Ok(Self::Q),
            "W" => Ok(Self::W),
            "E" => Ok(Self::E),
            "R" => Ok(Self::R),
            _ => Err("invalid value".into()),
        }
    }
}
impl ::std::convert::TryFrom<&str> for SkillOrderOptionOrderItem {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for SkillOrderOptionOrderItem {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
#[doc = "`SpellOption`"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct SpellOption {
    #[serde(deserialize_with = "::std::option::Option::deserialize")]
    pub ci: ::std::option::Option<Interval>,
    pub flags: ::std::vec::Vec<Flag>,
    #[doc = "Games played with this pair, whichever key each spell was on."]
    #[serde(skip_serializing_if = "::std::option::Option::is_none")]
    pub games: ::std::option::Option<u64>,
    pub n: u64,
    #[doc = "Summoner spell ids, D then F."]
    pub spells: [::std::num::NonZeroU64; 2usize],
    #[serde(deserialize_with = "::std::option::Option::deserialize")]
    pub wpa: ::std::option::Option<f64>,
}
#[doc = "The start head to head with the most played start (ADR-036)."]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct StartComparison {
    #[doc = "95% interval of `wpa`."]
    #[serde(skip_serializing_if = "::std::option::Option::is_none")]
    pub ci: ::std::option::Option<Interval>,
    #[doc = "False-discovery-adjusted p-value of no difference, across the patch."]
    pub q: f64,
    #[doc = "The most played start's items."]
    pub versus: ::std::vec::Vec<::std::num::NonZeroU64>,
    #[doc = "Win probability added by this start against `versus`."]
    pub wpa: f64,
}
#[doc = "One start: the items bought before leaving base, without supplies (potions, wards)."]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct StartOption {
    #[doc = "What is most often bought with this start, supplies included and repeated as bought: what an import lists."]
    pub buy: ::std::vec::Vec<::std::num::NonZeroU64>,
    #[serde(deserialize_with = "::std::option::Option::deserialize")]
    pub ci: ::std::option::Option<Interval>,
    #[serde(skip_serializing_if = "::std::option::Option::is_none")]
    pub comparison: ::std::option::Option<StartComparison>,
    pub flags: ::std::vec::Vec<Flag>,
    #[doc = "Games with this start."]
    pub games: u64,
    #[doc = "Data Dragon item ids, smallest first, each once."]
    pub items: ::std::vec::Vec<::std::num::NonZeroU64>,
    #[doc = "Decisions behind the estimate."]
    pub n: u64,
    #[doc = "Win probability added against the other starts; null when not estimated."]
    #[serde(deserialize_with = "::std::option::Option::deserialize")]
    pub wpa: ::std::option::Option<f64>,
}
#[doc = " Error types."]
pub mod error {
    #[doc = r" Error from a `TryFrom` or `FromStr` implementation."]
    pub struct ConversionError(::std::borrow::Cow<'static, str>);
    impl ::std::error::Error for ConversionError {}
    impl ::std::fmt::Display for ConversionError {
        fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> Result<(), ::std::fmt::Error> {
            ::std::fmt::Display::fmt(&self.0, f)
        }
    }
    impl ::std::fmt::Debug for ConversionError {
        fn fmt(&self, f: &mut ::std::fmt::Formatter<'_>) -> Result<(), ::std::fmt::Error> {
            ::std::fmt::Debug::fmt(&self.0, f)
        }
    }
    impl From<&'static str> for ConversionError {
        fn from(value: &'static str) -> Self {
            Self(value.into())
        }
    }
    impl From<String> for ConversionError {
        fn from(value: String) -> Self {
            Self(value.into())
        }
    }
}
