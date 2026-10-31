#![allow(clippy::redundant_closure_call)]
#![allow(clippy::needless_lifetimes)]
#![allow(clippy::match_single_binding)]
#![allow(clippy::clone_on_copy)]

#[doc = "`Champion`"]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct Champion {
    #[doc = "Data Dragon's physical damage rating."]
    pub attack: i64,
    #[doc = "Champion id, as the League client gives it."]
    pub id: ::std::num::NonZeroU64,
    #[doc = "Data Dragon's magic damage rating."]
    pub magic: i64,
}
#[doc = "Each champion's damage ratings on a patch, published at /{patch}/champions.json, and the cuts that make an enemy team physical, mixed or magic (ADR-074). An enemy team's magic share is the sum of its champions' magic ratings over the sum of their attack and magic ratings."]
#[derive(:: serde :: Deserialize, :: serde :: Serialize, Clone, Debug)]
#[serde(deny_unknown_fields)]
pub struct Champions {
    pub champions: ::std::vec::Vec<Champion>,
    #[doc = "From this, magic; in between, mixed."]
    #[serde(rename = "magicFrom")]
    pub magic_from: f64,
    #[doc = "Game patch, major.minor."]
    pub patch: ChampionsPatch,
    #[doc = "A team whose magic share is under this is physical."]
    #[serde(rename = "physicalBelow")]
    pub physical_below: f64,
    #[doc = "Contract major version."]
    #[serde(rename = "schemaVersion")]
    pub schema_version: ChampionsSchemaVersion,
}
#[doc = "Game patch, major.minor."]
#[derive(:: serde :: Serialize, Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
#[serde(transparent)]
pub struct ChampionsPatch(::std::string::String);
impl ::std::ops::Deref for ChampionsPatch {
    type Target = ::std::string::String;
    fn deref(&self) -> &::std::string::String {
        &self.0
    }
}
impl ::std::convert::From<ChampionsPatch> for ::std::string::String {
    fn from(value: ChampionsPatch) -> Self {
        value.0
    }
}
impl ::std::str::FromStr for ChampionsPatch {
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
impl ::std::convert::TryFrom<&str> for ChampionsPatch {
    type Error = self::error::ConversionError;
    fn try_from(value: &str) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl ::std::convert::TryFrom<::std::string::String> for ChampionsPatch {
    type Error = self::error::ConversionError;
    fn try_from(
        value: ::std::string::String,
    ) -> ::std::result::Result<Self, self::error::ConversionError> {
        value.parse()
    }
}
impl<'de> ::serde::Deserialize<'de> for ChampionsPatch {
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
#[doc = "Contract major version."]
#[derive(:: serde :: Serialize, Clone, Debug)]
#[serde(transparent)]
pub struct ChampionsSchemaVersion(i64);
impl ::std::ops::Deref for ChampionsSchemaVersion {
    type Target = i64;
    fn deref(&self) -> &i64 {
        &self.0
    }
}
impl ::std::convert::From<ChampionsSchemaVersion> for i64 {
    fn from(value: ChampionsSchemaVersion) -> Self {
        value.0
    }
}
impl ::std::convert::TryFrom<i64> for ChampionsSchemaVersion {
    type Error = self::error::ConversionError;
    fn try_from(value: i64) -> ::std::result::Result<Self, self::error::ConversionError> {
        if ![1_i64].contains(&value) {
            Err("invalid value".into())
        } else {
            Ok(Self(value))
        }
    }
}
impl<'de> ::serde::Deserialize<'de> for ChampionsSchemaVersion {
    fn deserialize<D>(deserializer: D) -> ::std::result::Result<Self, D::Error>
    where
        D: ::serde::Deserializer<'de>,
    {
        Self::try_from(<i64>::deserialize(deserializer)?)
            .map_err(|e| <D::Error as ::serde::de::Error>::custom(e.to_string()))
    }
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
