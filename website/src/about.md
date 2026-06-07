# About Nyaastats

Nyaastats tracks download statistics across torrents on Nyaa, aggregated across
individual torrents and visualized using data from the AniList API.

### Why?

Educational and entertainment purposes, as the saying goes. And as far as I
know, official streaming sites (Crunchyroll, Netflix, etc) don't publish
metrics publicly anywhere, so this seemed to be the closest I can get to
actual quantitative metrics.

Nyaa downloaders are also closer to my preferred subculture of anime fandom
anyway, vs the ratings of normies on MAL or whatever.

### What do the numbers actually represent?

The numbers are the `downloaded` count from Nyaa'a torrent tracker. Most
torrent clients will tell the tracker when they finish downloading a particular
torrent, which makes the number go up. This is also the same number the
"Completed Downloads" column on Nyaa's website.

The download numbers on this website per show/episode are aggregated across all
releases, using some fuzzy matching to compensate for different titles/filename
formats.

### Does one download equal one viewer?

Not necessarily. If you assume people only bother downloading one release per
episode, download totals do approximate unique viewers though.

### Which torrents are included?

Only torrents in the "English-translated Anime" category. 

### What is "Endurance"?

**Endurance** is a metric I made up that attempts to measure how well a show maintains its audience after the first episode.

It's calculated as: *average downloads of episodes 2 and later* divided by *episode 1 downloads*.

- **100%** means later episodes get the same downloads as episode 1
- **80%** means later episodes average 80% of episode 1's downloads (typical drop-off)
- **Above 100%** is rare—it means the show *grew* in popularity after premiering

We cap at episode 14 to keep comparisons within a single season, even for shows that continue longer.

Presumably shows with unusually high endurance kept viewers engaged. Shows with low endurance had many people try episode 1 but drop it later.

### What is "Late Starters"?

**Late Starters** is another metric I made up to try and identify "sleeper hits"—shows that weren't hyped but people picked up later.

It's calculated as the *episode 1 downloads in the first week* divided by *episode 1 downloads after the first week*.

- **10%** means most people downloaded episode 1 right away.
- **50%** means half the people started the show weeks later.

### What are the "rank delta" charts?

These compare how a show ranks on **nyaa downloads** versus how it ranks on an
external **rating** — [MyAnimeList](https://myanimelist.net) score (via the
[Jikan API](https://jikan.moe)) and [AniList](https://anilist.co) average score.

For each show we compute its download rank and its rating rank within the season,
then take the difference (`download rank − rating rank`):

- **Positive (green)** — the show is rated highly but comparatively few people
  download it: an *underrated* pick by nyaa standards.
- **Negative (red)** — downloads outrun the critical reception: popular to grab
  but rated lower.

The companion scatterplot puts the rating score on the x-axis and total downloads
(log scale) on the y-axis. The dashed line is a least-squares fit of downloads
against score (computed in log space, since downloads span orders of magnitude),
and the short colored segment on each point is its *residual* — the gap to the
trend. Shows sitting well above the line over-download for their score (green
residual), while those below under-download (red). The biggest outliers are
labelled directly. Shows without a matching MAL/AniList entry are omitted.

### What is the Niconico column?

Some anime air on Niconico's official live broadcasts (ニコ生), where viewers are
shown a 5-point satisfaction survey (公式アンケート) at the end of each episode:
『とても良かった』(very good) → 『良くなかった』(not good). The **Niconico** column
is the average, across a show's episodes, of the percentage of live viewers who
picked 『とても良かった』— the headline number the Niconico community tracks.

This data comes from the fan-run database at
[nicolive-anime-survey.info](https://nicolive-anime-survey.info/). Only shows that
actually aired on a Niconico live broadcast have survey data, so many shows show a
"—". Niconico's live-broadcast audience skews differently from nyaa downloaders,
which is part of what makes the comparison interesting. (Note: this is the survey
*rating* only — Niconico view counts aren't part of this source.)

### What is the "Season at a glance" card grid?

A uniform card per show (unlike the area-weighted treemap), small enough to
screenshot a whole season. Each card packs:

- **Three sparklines** — downloads per episode, weekly rank over time, and the
  Niconico 『とても良かった』% per episode (where available).
- **A rank radar** with four spokes — nyaa downloads, MyAnimeList, AniList, and
  Niconico. Each spoke is the show's *rank within the season* on that metric,
  normalized so the season-best reaches the outer edge and a missing metric
  collapses to the centre. A big, full diamond is a show that's near the top on
  everything; a lopsided shape shows where a show over- or under-performs.

Use the **Sort cards by** selector to reorder (descending, left-to-right); it
defaults to nyaa downloads.

### Why group shows by premiere size?

Shows with huge premieres (like sequels to popular series) behave differently
than smaller shows. Also it keeps the beeswarm/scatterplots mangeable.

### How do you handle different subtitle groups and video qualities?

We sum downloads across all releases of the same episode. If SubGroup A's 1080p
release got 10K downloads and SubGroup B's 720p got 5K, we report 15K total for
that episode.

This assumes most viewers pick one version to watch. It may slightly overcount
if many people download multiple versions, or undercount if we miss some
releases.

### How do you define a "season"?

However AniList does.

### How fresh is the data?

The scraper runs hourly to collect new torrents and update download counts.
Weekly statistics are computed once per week. For ongoing seasons, you're
seeing data up to the most recent weekly update.

### Why is the data for some show missing/wrong/weird?

The matching process is fuzzy, and some torrent releases have weird filenames,
and some shows just don't fit nicely into the assumptions made by the parser
(off-season, episode 0s/OVAs). If you think you can improve any of the methods,
[Open an issue on GitHub](https://github.com/hiinaspace/nyaastats/issues). 

### How are movies tracked?

The [Movies](/movies) page tracks standalone movies, OVAs, and specials separately from the weekly seasonal rankings.

**How it works:**

1. We query AniList for anime with format MOVIE, ONA, or SPECIAL that started airing during the tracking period (June 2025 – March 2026).
2. We filter to **released, single-episode** entries only — this excludes episodic ONAs (which are really seasonal shows) and unreleased films.
3. Some entries that slip through (e.g., episodic ONAs that AniList misclassifies) are manually excluded.
4. Torrents are fuzzy-matched to these movies the same way seasonal shows are, with manual overrides for titles that don't match well (e.g., Demon Slayer, Chainsaw Man).
5. Downloads are aggregated in **weekly buckets** since older movies are only scraped weekly.

Because AniList sometimes assigns movies to seasons outside the tracking period (e.g., a movie that aired in Fall 2025 but is tagged as Summer 2025), we query by date range rather than by season.

### Where's the data before Fall 2025?

I only started scraping in June of 2025, so that's the first complete season I
have. I may add (incomplete) versions of previous seasons later.

### Can I have the raw data?

Yeah, email me and I can send you a snapshot of the sqlite database.

### How does this all actually work?

For technical details about the scraper, ETL pipeline, and this visualization website, see
the [GitHub repository](https://github.com/hiinaspace/nyaastats).

### Why are Nyaa downloaders' tastes so shit?

Unfortunately, I can only provide the data, not moral judgement.

<div class="note">

Nyaastats is a unofficial project. Data is provided for educational and entertainment purposes. Nyaa.si data is publicly available. AniList data is used under their API terms.

</div>
