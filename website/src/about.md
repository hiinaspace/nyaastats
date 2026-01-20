# About Nyaastats

Nyaastats tracks download statistics for anime torrents from [Nyaa.si](https://nyaa.si), one of the largest anime torrent sites. This page explains how the data works and what the numbers mean.

---

## Understanding the Data

### What do the download numbers actually represent?

The numbers show how many times torrents were fully downloaded, as reported by BitTorrent trackers. When you see "50K downloads" for an episode, it means torrent files for that episode were downloaded to completion approximately 50,000 times.

### Does one download equal one viewer?

Not exactly, but it's a reasonable proxy. Some people download multiple versions (different quality, different subtitle groups), while others stream or use other sources entirely. We assume the average viewer downloads roughly one version per episode, so the totals approximate unique viewers within this community.

### Why track torrents instead of streaming numbers?

Streaming platforms don't publish detailed per-show statistics. Torrent downloads are publicly observable and provide a consistent, measurable signal of fan interest—particularly among international viewers who may not have legal streaming access.

### Which torrents are included?

We track torrents from Nyaa.si tagged as anime. The data is matched to shows in the [AniList](https://anilist.co) database using fuzzy title matching. We exclude batch torrents (full-season packs) and repack/v2 releases to avoid double-counting.

---

## The Metrics

### What is Endurance?

**Endurance** measures how well a show maintains its audience after the first episode.

It's calculated as: *average downloads of episodes 2–14* divided by *episode 1 downloads*.

- **100%** means later episodes get the same downloads as episode 1
- **80%** means later episodes average 80% of episode 1's downloads (typical drop-off)
- **Above 100%** is rare—it means the show *grew* in popularity after premiering

We cap at episode 14 to keep comparisons within a single season, even for shows that continue longer.

**What it reveals:** Shows with unusually high endurance kept viewers engaged. Shows with low endurance had many people try episode 1 but not continue.

### What are Late Starters?

**Late Starters** measures what percentage of episode 1 downloads came *after* the first week.

- **10%** means most people downloaded episode 1 right away (hype-driven premiere)
- **40%** means many people started the show weeks later (word-of-mouth growth)

**What it reveals:** High late starter percentages often indicate "sleeper hits"—shows that weren't hyped but gained audience through recommendations and positive buzz after airing.

### Why group shows by premiere size in some charts?

Shows with huge premieres (like sequels to popular series) behave differently than smaller shows. Grouping by episode 1 download size lets you compare apples to apples—a small show with great endurance vs. other small shows, rather than against blockbusters.

---

## Methodology Details

### How do you handle different subtitle groups and video qualities?

We sum downloads across all releases of the same episode. If SubGroup A's 1080p release got 10K downloads and SubGroup B's 720p got 5K, we report 15K total for that episode.

This assumes most viewers pick one version to watch. It may slightly overcount if many people download multiple versions, or undercount if we miss some releases.

### How do you match torrents to anime shows?

Torrent titles are messy—they include group names, quality tags, and varying title formats. We use fuzzy string matching (edit distance) to find the closest AniList entry, with manual overrides for tricky cases.

Some torrents can't be matched reliably and are excluded from the statistics.

### How do you define a "season"?

Anime seasons follow the standard industry calendar:
- **Winter**: January–March
- **Spring**: April–June
- **Summer**: July–September
- **Fall**: October–December

Shows are assigned to seasons based on their air date in AniList. Shows that span multiple seasons appear in their starting season.

### How fresh is the data?

The scraper runs hourly to collect new torrents and update download counts. Weekly statistics are computed once per week. For ongoing seasons, you're seeing data up to the most recent weekly update.

---

## Limitations

### What doesn't this data capture?

- **Streaming viewers**: Most anime fans watch via Crunchyroll, Netflix, etc.
- **Japanese domestic audience**: Nyaa is primarily used by international fans
- **Direct downloads**: Some people use file hosting sites instead of torrents
- **Regional variation**: We can't break down by country or region

This data represents one slice of anime fandom—engaged international fans who use torrents—not the complete picture.

### Why might some shows be missing or have low numbers?

- **Streaming exclusives**: Shows only on Netflix/etc. may have fewer torrent releases
- **Niche shows**: Less popular genres have smaller torrent communities
- **Matching failures**: Some torrents couldn't be matched to AniList entries
- **Release delays**: Fansub releases may lag behind simulcasts

---

## More Information

For technical details about the scraper, ETL pipeline, and data formats, see the [GitHub repository](https://github.com/hiinaspace/nyaastats).

Questions or feedback? [Open an issue on GitHub](https://github.com/hiinaspace/nyaastats/issues).

---

<div class="note">
  Data is provided for educational and entertainment purposes. Nyaa.si data is publicly available; AniList data is used under their API terms.
</div>
