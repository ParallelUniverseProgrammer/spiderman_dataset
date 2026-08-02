"""
Build the Spider-Man media database.

Schema (normalized, linked):
  media_works   - master table, one row per titled work
  movies        - detail table (1:1 with media_works where media_type='movie')
  tv_shows      - detail table (1:1 with media_works where media_type='tv_show')
  games         - detail table (1:1 with media_works where media_type='game')
  platforms     - lookup of game platforms
  game_platforms- junction table (game_id, platform_id) many:many
  franchises    - lookup of franchises / universes
  people        - lookup of notable people (actors/voice actors/directors)
  work_people   - junction (work_id, person_id, role) many:many

After building, exports every table to data/*.csv and a flat combined CSV.
"""

import csv
import os
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
os.makedirs(DATA, exist_ok=True)

DB_PATH = os.path.join(HERE, "spiderman.db")

# Wipe any prior copy so the build is idempotent.
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA foreign_keys = ON")
cur = conn.cursor()

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
cur.executescript("""
CREATE TABLE franchises (
    id          INTEGER PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,
    description TEXT
);

CREATE TABLE media_works (
    id            INTEGER PRIMARY KEY,
    title         TEXT NOT NULL,
    release_year  INTEGER,
    release_date  TEXT,
    media_type    TEXT NOT NULL CHECK (media_type IN ('movie','tv_show','game')),
    franchise_id  INTEGER REFERENCES franchises(id),
    notes         TEXT
);

CREATE TABLE movies (
    work_id                  INTEGER PRIMARY KEY REFERENCES media_works(id),
    sub_type                 TEXT,
    studio                   TEXT,
    distributor              TEXT,
    director                 TEXT,
    writer                   TEXT,
    producer                 TEXT,
    runtime_minutes          INTEGER,
    mpaa_rating              TEXT,
    budget_usd               INTEGER,
    box_office_worldwide_usd INTEGER,
    spider_man_actor         TEXT,
    rotten_tomatoes_score    INTEGER,
    metacritic_score         INTEGER,
    imdb_score               REAL
);

CREATE TABLE tv_shows (
    work_id                INTEGER PRIMARY KEY REFERENCES media_works(id),
    sub_type               TEXT,
    format                 TEXT,
    network                TEXT,
    start_year             INTEGER,
    end_year               INTEGER,
    seasons                INTEGER,
    episodes               INTEGER,
    head_writer            TEXT,
    director               TEXT,
    voice_actor_spider_man TEXT,
    status                 TEXT
);

CREATE TABLE games (
    work_id            INTEGER PRIMARY KEY REFERENCES media_works(id),
    developer          TEXT,
    publisher          TEXT,
    genre              TEXT,
    engine             TEXT,
    directors          TEXT,
    metacritic_score   TEXT,
    esrb_rating        TEXT,
    universe           TEXT,
    notes              TEXT
);

CREATE TABLE platforms (
    id       INTEGER PRIMARY KEY,
    name     TEXT UNIQUE NOT NULL
);

CREATE TABLE game_platforms (
    game_id      INTEGER REFERENCES media_works(id),
    platform_id  INTEGER REFERENCES platforms(id),
    PRIMARY KEY (game_id, platform_id)
);

CREATE TABLE people (
    id    INTEGER PRIMARY KEY,
    name  TEXT UNIQUE NOT NULL
);

CREATE TABLE work_people (
    work_id   INTEGER REFERENCES media_works(id),
    person_id INTEGER REFERENCES people(id),
    role      TEXT NOT NULL,
    PRIMARY KEY (work_id, person_id, role)
);
""")

# ---------------------------------------------------------------------------
# Franchises
# ---------------------------------------------------------------------------
franchises = [
    ("Early TV films", "1977-1981 CBS TV-movie compilations from The Amazing Spider-Man series"),
    ("Toei Japanese Spider-Man", "1978 Toei tokusatsu series & theatrical spin-off (Takuya Yamashiro)"),
    ("Sam Raimi trilogy", "Tobey Maguire films 2002-2007 directed by Sam Raimi"),
    ("Marc Webb duology", "Andrew Garfield films 2012-2014 directed by Marc Webb"),
    ("MCU", "Marvel Cinematic Universe - Tom Holland Spider-Man films"),
    ("Spider-Verse", "Sony Pictures Animation animated Spider-Verse films"),
    ("Sony Spider-Man Universe (SSU)", "Sony live-action spin-off films (Venom, Morbius, etc.)"),
    ("Insomniac Spider-Man universe", "PlayStation/PC Insomniac Games Marvel's Spider-Man series (Earth-1048)"),
    ("Standalone", "Standalone / non-franchise Spider-Man media"),
    ("LEGO Marvel crossover", "LEGO Marvel games featuring Spider-Man as a major character"),
    ("Movie tie-in", "Video games directly tieing in to a Spider-Man film release"),
    ("The Electric Company", "PBS children's show that featured Spidey Super Stories"),
]
for name, desc in franchises:
    cur.execute("INSERT INTO franchises(name, description) VALUES (?,?)", (name, desc))

FR = {n: i for i, (n, _) in enumerate(franchises, start=1)}

# ---------------------------------------------------------------------------
# Helper to insert a media_work row and return its id
# ---------------------------------------------------------------------------
def add_work(title, year, release_date, media_type, franchise_name, notes=""):
    fid = FR[franchise_name]
    cur.execute(
        "INSERT INTO media_works(title, release_year, release_date, media_type, franchise_id, notes) "
        "VALUES (?,?,?,?,?,?)",
        (title, year, release_date, media_type, fid, notes),
    )
    return cur.lastrowid


# ---------------------------------------------------------------------------
# MOVIES
# ---------------------------------------------------------------------------
movies_data = [
    # title, year, date, franchise, notes, sub_type, studio, distributor, director, writer, producer, runtime, rating, budget, boxoffice, actor, rt, meta, imdb
    ("Spider-Man", 1977, "1977-09-14", "Early TV films", "TV movie pilot for The Amazing Spider-Man series", "TV film", "Danchuk Productions; Marvel Productions", "CBS", "E.W. Swackhamer", "Alvin Boretz", "Danchuk Productions", 98, None, None, None, "Nicholas Hammond", None, None, None),
    ("Spider-Man Strikes Back", 1978, "1978-05-04", "Early TV films", "Composite of two TV episodes; later theatrically released in Europe", "TV film", "Danchuk Productions; Marvel Productions", "CBS", "Ron Satlof", "Robert Janes", "Danchuk Productions", 90, None, None, None, "Nicholas Hammond", None, None, None),
    ("Spider-Man: The Dragon's Challenge", 1981, "1981-09-09", "Early TV films", "Composite of TV episodes; theatrically released in Europe", "TV film", "Danchuk Productions; Marvel Productions", "CBS", "Don McDougall", "Robert Janes", "Danchuk Productions", 90, None, None, None, "Nicholas Hammond", None, None, None),
    ("Spider-Man (Toei)", 1978, "1978-07-22", "Toei Japanese Spider-Man", "Theatrical spin-off of the Toei tokusatsu TV series; non-Peter-Parker lead", "live-action", "Toei Company", "Toei Company", "Kōichi Takamoto", "Susumu Takahisa; Shuji Kataoka; Kōichi Takamoto", "Toei Company", 74, None, None, None, "Shinji Todo (Takuya Yamashiro)", None, None, None),
    ("Spider-Man", 2002, "2002-05-03", "Sam Raimi trilogy", "Nominated for Best Visual Effects and Best Sound at 75th Academy Awards", "live-action", "Columbia Pictures", "Sony Pictures Releasing", "Sam Raimi", "David Koepp", "Laura Ziskin; Ian Bryce", 121, "PG-13", 139000000, 825000000, "Tobey Maguire", 90, 73, 7.4),
    ("Spider-Man 2", 2004, "2004-06-30", "Sam Raimi trilogy", "Won Best Visual Effects at 77th Academy Awards", "live-action", "Columbia Pictures", "Sony Pictures Releasing", "Sam Raimi", "Alvin Sargent", "Laura Ziskin; Ian Bryce", 127, "PG-13", 200000000, 789000000, "Tobey Maguire", 93, 83, 7.3),
    ("Spider-Man 3", 2007, "2007-05-04", "Sam Raimi trilogy", "Spider-Man 4 was cancelled in 2010", "live-action", "Columbia Pictures", "Sony Pictures Releasing", "Sam Raimi", "Sam Raimi; Ivan Raimi; Alvin Sargent", "Laura Ziskin; Avi Arad; Grant Curtis", 139, "PG-13", 258000000, 890900000, "Tobey Maguire", 63, 59, 6.2),
    ("The Amazing Spider-Man", 2012, "2012-07-03", "Marc Webb duology", "Reboot of the franchise", "live-action", "Columbia Pictures; Marvel Entertainment", "Sony Pictures Releasing", "Marc Webb", "James Vanderbilt; Alvin Sargent; Steve Kloves", "Avi Arad; Matt Tolmach; Laura Ziskin", 136, "PG-13", 230000000, 758000000, "Andrew Garfield", 71, 62, 6.9),
    ("The Amazing Spider-Man 2", 2014, "2014-05-02", "Marc Webb duology", "Sequels and Sinister Six spin-off were cancelled", "live-action", "Columbia Pictures; Marvel Entertainment", "Sony Pictures Releasing", "Marc Webb", "Alex Kurtzman; Roberto Orci; Jeff Pinkner", "Avi Arad; Matt Tolmach", 142, "PG-13", 292000000, 709000000, "Andrew Garfield", 51, 53, 6.6),
    ("Spider-Man: Homecoming", 2017, "2017-07-07", "MCU", "First MCU Spider-Man solo film; co-production with Marvel Studios", "live-action", "Columbia Pictures; Marvel Studios; Pascal Pictures", "Sony Pictures Releasing", "Jon Watts", "Jonathan Goldstein; John Francis Daley; Christopher Ford; Chris McKenna; Erik Sommers", "Kevin Feige; Amy Pascal", 133, "PG-13", 175000000, 880000000, "Tom Holland", 92, 73, 7.4),
    ("Spider-Man: Into the Spider-Verse", 2018, "2018-12-14", "Spider-Verse", "Won Best Animated Feature at 91st Academy Awards", "animated", "Sony Pictures Animation", "Sony Pictures Releasing", "Bob Persichetti; Peter Ramsey; Rodney Rothman", "Phil Lord; Rodney Rothman", "Phil Lord; Christopher Miller; Amy Pascal; Avi Arad; Christina Steinberg", 117, "PG", 90000000, 384000000, "Shameik Moore (Miles Morales)", 97, 87, 8.6),
    ("Spider-Man: Far From Home", 2019, "2019-07-02", "MCU", "First Spider-Man film to gross over $1 billion", "live-action", "Columbia Pictures; Marvel Studios; Pascal Pictures", "Sony Pictures Releasing", "Jon Watts", "Chris McKenna; Erik Sommers", "Kevin Feige; Amy Pascal", 129, "PG-13", 160000000, 1132000000, "Tom Holland", 90, 69, 7.5),
    ("Spider-Man: No Way Home", 2021, "2021-12-17", "MCU", "Features Tobey Maguire and Andrew Garfield multiverse cameos", "live-action", "Columbia Pictures; Marvel Studios; Pascal Pictures", "Sony Pictures Releasing", "Jon Watts", "Chris McKenna; Erik Sommers", "Kevin Feige; Amy Pascal", 148, "PG-13", 200000000, 1952000000, "Tom Holland", 93, 71, 8.2),
    ("Spider-Man: Across the Spider-Verse", 2023, "2023-06-02", "Spider-Verse", "First part of a two-part sequel", "animated", "Sony Pictures Animation", "Sony Pictures Releasing", "Joaquim Dos Santos; Kemp Powers; Justin K. Thompson", "Phil Lord; Christopher Miller; David Callaham", "Phil Lord; Christopher Miller; Amy Pascal; Christina Steinberg", 140, "PG", 100000000, 690000000, "Shameik Moore (Miles Morales)", 95, 86, 8.6),
    ("Spider-Man: Beyond the Spider-Verse", None, None, "Spider-Verse", "Upcoming; release delayed, year unconfirmed", "animated", "Sony Pictures Animation", "Sony Pictures Releasing", "Bob Persichetti", "Phil Lord; Christopher Miller", "Phil Lord; Christopher Miller; Amy Pascal", None, None, None, None, "Shameik Moore (Miles Morales)", None, None, None),
    ("Spider-Man: Brand New Day", 2026, "2026-07-31", "MCU", "Announced; release date set for July 2026", "live-action", "Columbia Pictures; Marvel Studios; Pascal Pictures", "Sony Pictures Releasing", "Destin Daniel Cretton", "Chris McKenna; Erik Sommers", "Kevin Feige; Amy Pascal", None, None, None, None, "Tom Holland", None, None, None),
    # SSU spin-offs
    ("Venom", 2018, "2018-10-05", "Sony Spider-Man Universe (SSU)", "First SSU film", "SSU spin-off", "Columbia Pictures; Marvel; Tencent", "Sony Pictures Releasing", "Ruben Fleischer", "Jeff Pinkner; Scott Rosenberg; Kelly Marcel", "Avi Arad; Matt Tolmach; Amy Pascal", 112, "PG-13", 116000000, 856000000, "Tom Hardy (Eddie Brock / Venom)", 30, 35, 6.6),
    ("Venom: Let There Be Carnage", 2021, "2021-10-01", "Sony Spider-Man Universe (SSU)", "", "SSU spin-off", "Columbia Pictures; Marvel", "Sony Pictures Releasing", "Andy Serkis", "Kelly Marcel", "Avi Arad; Matt Tolmach; Amy Pascal; Tom Hardy", 97, "PG-13", 110000000, 506000000, "Tom Hardy (Eddie Brock / Venom)", 71, 47, 5.9),
    ("Morbius", 2022, "2022-04-01", "Sony Spider-Man Universe (SSU)", "", "SSU spin-off", "Columbia Pictures; Marvel", "Sony Pictures Releasing", "Daniel Espinosa", "Matt Sazama; Burk Sharpless", "Avi Arad; Matt Tolmach", 104, "PG-13", 83000000, 167000000, "Jared Leto (Dr. Michael Morbius)", 15, 35, 5.2),
    ("Madame Web", 2024, "2024-02-14", "Sony Spider-Man Universe (SSU)", "", "SSU spin-off", "Columbia Pictures; Marvel", "Sony Pictures Releasing", "S.J. Clarkson", "Claire Parker; S.J. Clarkson", "Avi Arad; Lorenzo di Bonaventura", 116, "PG-13", 100000000, 100000000, "Dakota Johnson (Cassandra Webb)", 11, 29, 4.0),
    ("Kraven the Hunter", 2024, "2024-12-13", "Sony Spider-Man Universe (SSU)", "Final film in the SSU", "SSU spin-off", "Columbia Pictures; Marvel", "Sony Pictures Releasing", "J.C. Chandor", "Art Marcum; Matt Holloway; Richard Wenk", "Avi Arad; Matt Tolmach", 127, "R", 130000000, 61000000, "Aaron Taylor-Johnson (Sergei Kravinoff)", 15, 35, 5.4),
    ("Venom: The Last Dance", 2024, "2024-10-25", "Sony Spider-Man Universe (SSU)", "", "SSU spin-off", "Columbia Pictures; Marvel", "Sony Pictures Releasing", "Kelly Marcel", "Kelly Marcel", "Avi Arad; Matt Tolmach; Amy Pascal; Tom Hardy", 109, "PG-13", 120000000, 478000000, "Tom Hardy (Eddie Brock / Venom)", 41, 41, 6.0),
    ("El Muerto", None, None, "Sony Spider-Man Universe (SSU)", "In development; indefinitely delayed; release date TBD", "SSU spin-off", "Columbia Pictures", "Sony Pictures Releasing", None, None, None, None, None, None, None, "Bad Bunny (Juan-Carlos Estrada Sanchez)", None, None, None),
]

movie_work_ids = []
for row in movies_data:
    (title, year, date, franch, notes, sub_type, studio, distr, director, writer, producer,
     runtime, rating, budget, box, actor, rt, meta, imdb) = row
    wid = add_work(title, year, date, "movie", franch, notes)
    movie_work_ids.append((wid, actor))
    cur.execute("""INSERT INTO movies(work_id, sub_type, studio, distributor, director, writer,
                     producer, runtime_minutes, mpaa_rating, budget_usd,
                     box_office_worldwide_usd, spider_man_actor, rotten_tomatoes_score,
                     metacritic_score, imdb_score)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (wid, sub_type, studio, distr, director, writer, producer, runtime, rating,
                 budget, box, actor, rt, meta, imdb))

# ---------------------------------------------------------------------------
# TV SHOWS
# ---------------------------------------------------------------------------
tv_data = [
    # title, year, date, franchise, notes, sub_type, format, network, start, end, seasons, eps, head_writer, director, voice_actor, status
    ("Spidey Super Stories", 1974, None, "The Electric Company", "Segment on The Electric Company; first live-action Spider-Man portrayal", "live-action", "sketch segment", "PBS (The Electric Company)", 1974, 1977, None, None, None, None, "Danny Seagren", "ended"),
    ("The Amazing Spider-Man", 1977, None, "Early TV films", "Live-action CBS series starring Nicholas Hammond; canceled after two seasons", "live-action", "live-action series", "CBS", 1977, 1979, 2, 13, None, None, "Nicholas Hammond", "ended"),
    ("Spider-Man (Japanese TV series)", 1978, None, "Toei Japanese Spider-Man", "Toei tokusatsu series; Spider-Man is Takuya Yamashiro, not Peter Parker; introduced giant-robot tradition carried into Super Sentai", "live-action", "tokusatsu series", "Tokyo Channel 12 (TV Tokyo)", 1978, 1979, 1, 41, None, None, "Shinji Todo (Takuya Yamashiro)", "ended"),
    ("Spider-Noir", 2026, "2026-05-25", "Spider-Verse", "Live-action Spider-Man Noir series spinning out of the Spider-Verse films; premiered May 25 2026 on MGM+; 8 episodes", "live-action", "live-action series", "MGM+ / Prime Video", 2026, 2026, 1, 8, None, None, "Nicolas Cage", "current"),
    # Animated
    ("Spider-Man (1967 TV series)", 1967, "1967-09-09", "Standalone", "First Spider-Man animated series; theme song became iconic; first season Grantray-Lawrence, then Ralph Bakshi", "animated", "animated series", "ABC", 1967, 1970, 3, 52, "Grant Simmons; Clyde Geronimi; Sid Marcus (s1); Ralph Bakshi (s2+)", None, "Paul Soles", "ended"),
    ("Spider-Man (1981 TV series)", 1981, "1981-09-12", "Standalone", "First Marvel Productions Spider-Man series; syndicated", "animated", "animated series", "Syndication", 1981, 1982, 1, 26, None, None, "Ted Schwartz", "ended"),
    ("Spider-Man and His Amazing Friends", 1981, "1981-09-12", "Standalone", "Spider-Man, Iceman and Firestar team-up series on NBC", "animated", "animated series", "NBC", 1981, 1983, 3, 24, None, "Don Jurwich", "Dan Gilvezan", "ended"),
    ("Spider-Man: The Animated Series", 1994, "1994-11-19", "Standalone", "Longest Spider-Man series until Ultimate Spider-Man; one story arc per season; 65 episodes", "animated", "animated series", "Fox Kids", 1994, 1998, 5, 65, "John Semper Jr.", None, "Christopher Daniel Barnes", "ended"),
    ("Spider-Man Unlimited", 1999, "1999-10-02", "Standalone", "Spider-Man transported to Counter-Earth; canceled after one season", "animated", "animated series", "Fox Kids", 1999, 2001, 1, 13, "Michael Reaves (1-6); Robert Gregory Browne & Larry Brody (7-13)", "Patrick Archibald", "Rino Romano", "ended"),
    ("Spider-Man: The New Animated Series", 2003, "2003-07-11", "Movie tie-in", "CGI series on MTV continuing the 2002 film continuity", "animated", "CGI animated series", "MTV", 2003, 2003, 1, 13, None, None, "Neil Patrick Harris", "ended"),
    ("The Spectacular Spider-Man", 2008, "2008-03-08", "Standalone", "Acclaimed series based on Lee/Ditko/Romita and Ultimate comics; ended when Sony returned animation rights to Marvel", "animated", "animated series", "The CW / Disney XD", 2008, 2009, 2, 26, "Greg Weisman", None, "Josh Keaton", "ended"),
    ("Ultimate Spider-Man", 2012, "2012-04-01", "Standalone", "Spider-Man leads a S.H.I.E.L.D. trainee team; 104 episodes over 4 seasons", "animated", "animated series", "Disney XD", 2012, 2017, 4, 104, "Brian Michael Bendis; Paul Dini", None, "Drake Bell", "ended"),
    ("Spider-Man (2017 TV series)", 2017, "2017-08-19", "Standalone", "Peter teams with Miles Morales, Gwen Stacy and Anya Corazon", "animated", "animated series", "Disney XD", 2017, 2020, 3, 58, "Kevin Shinick", None, "Robbie Daymond", "ended"),
    ("Spidey and His Amazing Friends", 2021, "2021-08-06", "Standalone", "Preschool series on Disney Junior", "animated", "animated series (preschool)", "Disney Junior", 2021, None, 4, 103, "Becca Topol", "Darren Bachynski (s1-2); Mitch Stookey (s3+)", "Benjamin Valic (s1-2); Alkaio Thiele (s3+)", "current"),
    ("Your Friendly Neighborhood Spider-Man", 2025, "2025-01-29", "MCU", "MCU animated series on Disney+; alternate timeline where Norman Osborn mentors Peter instead of Tony Stark", "animated", "animated series", "Disney+", 2025, None, 1, 10, "Jeff Trammell", "Mel Zwyer; Liza Singer; Stu Livingston", "Hudson Thames", "current"),
]

for row in tv_data:
    (title, year, date, franch, notes, sub_type, fmt, network, start, end, seasons, eps,
     head_writer, director, voice, status) = row
    wid = add_work(title, year, date, "tv_show", franch, notes)
    cur.execute("""INSERT INTO tv_shows(work_id, sub_type, format, network, start_year, end_year,
                     seasons, episodes, head_writer, director, voice_actor_spider_man, status)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (wid, sub_type, fmt, network, start, end, seasons, eps, head_writer, director, voice, status))

# ---------------------------------------------------------------------------
# GAMES
# ---------------------------------------------------------------------------
# title, year, date, franchise, notes, developer, publisher, platforms(list), genre, engine, directors, meta, esrb, universe
games_data = [
    ("Spider-Man (1982)", 1982, None, "Standalone", "First Spider-Man video game; climb skyscraper, defuse Green Goblin bombs", "Parker Brothers", "Parker Brothers", ["Atari 2600", "Magnavox Odyssey 2"], "action", None, None, None, None, "Standalone"),
    ("Questprobe featuring Spider-Man", 1984, None, "Standalone", "Part of the Questprobe text/graphic adventure series", "Adventure International", "Adventure International", ["Amstrad CPC", "Apple II", "Commodore 64", "Commodore 16", "Atari 8-bit", "ZX Spectrum", "IBM PC"], "graphic adventure", None, "Scott Adams", None, None, "Standalone"),
    ("The Amazing Spider-Man and Captain America in Dr. Doom's Revenge!", 1989, None, "Standalone", "Comic-panel storytelling crossover", "Paragon Software Corporation", "Medallist (MicroProse)", ["MS-DOS", "Amiga", "Atari ST", "Amstrad CPC", "ZX Spectrum", "Commodore 64"], "action/fighting", None, None, None, None, "Standalone"),
    ("The Amazing Spider-Man (1990 computer)", 1990, None, "Standalone", "Home computer release", "Oxford Digital Enterprises", "Paragon Software", ["Amiga", "MS-DOS", "Commodore 64", "Atari ST"], "puzzle-action", None, None, None, None, "Standalone"),
    ("The Amazing Spider-Man (1990 Game Boy)", 1990, None, "Standalone", "First Game Boy Spider-Man; start of Game Boy trilogy", "Rare", "LJN/Nintendo", ["Game Boy"], "action platformer", None, None, None, None, "Standalone"),
    ("The Punisher: The Ultimate Payback!", 1991, None, "Standalone", "Spider-Man appears as supporting character", "Beam Software (Krome Studios Melbourne)", "Acclaim Entertainment", ["Game Boy"], "light gun/shooter", None, None, None, None, "Standalone"),
    ("Spider-Man vs. The Kingpin", 1991, "1991-01-01", "Standalone", "Released 1990 Master System/Genesis, 1992 Game Gear, 1993 Sega CD", "Technopop", "Sega", ["Sega Genesis", "Master System", "Game Gear", "Sega CD"], "action platformer", None, None, None, None, "Standalone"),
    ("Spider-Man: The Video Game", 1991, None, "Standalone", "4-player arcade cabinet", "Sega", "Sega", ["Arcade (Sega System 32)"], "beat 'em up/platformer", None, None, None, None, "Standalone"),
    ("The Amazing Spider-Man 2 (1992)", 1992, None, "Standalone", "Game Boy trilogy part 2", "Bits Studios", "LJN", ["Game Boy"], "side-scrolling beat 'em up", None, None, None, None, "Standalone"),
    ("Spider-Man: Return of the Sinister Six", 1992, None, "Standalone", "First NES Spider-Man", "Bits Studios", "LJN/Flying Edge", ["NES", "Master System", "Game Gear"], "action platformer", None, None, None, None, "Standalone"),
    ("Spider-Man and the X-Men in Arcade's Revenge", 1992, None, "Standalone", "Crossover with the X-Men", "Software Creations", "LJN", ["Super NES", "Genesis", "Game Gear", "Game Boy"], "action platformer", None, None, None, None, "Standalone"),
    ("The Amazing Spider-Man 3: Invasion of the Spider-Slayers", 1993, None, "Standalone", "Game Boy trilogy part 3", "Bits Studios", "LJN", ["Game Boy"], "action platformer", None, None, None, None, "Standalone"),
    ("Spider-Man and Venom: Maximum Carnage", 1994, None, "Standalone", "Based on the Maximum Carnage comic arc", "Software Creations", "LJN", ["Super NES", "Genesis"], "beat 'em up", None, None, None, None, "Standalone"),
    ("The Amazing Spider-Man: Lethal Foes", 1995, None, "Standalone", "Japan-only Super Famicom release", "Argent; Epoch Co.", "Epoch", ["Super Famicom"], "action platformer", None, None, None, None, "Standalone"),
    ("Venom/Spider-Man: Separation Anxiety", 1995, None, "Standalone", "Sequel to Maximum Carnage", "Software Creations", "Acclaim Entertainment", ["Super NES", "Genesis"], "beat 'em up", None, None, None, None, "Standalone"),
    ("Spider-Man (1995 video game)", 1995, None, "Standalone", "Based on the 1994 animated series", "Western Technologies", "LJN/Acclaim Entertainment", ["Sega Genesis/Mega Drive", "SNES"], "action platformer", None, None, None, None, "Standalone"),
    ("The Amazing Spider-Man: Web of Fire", 1996, None, "Standalone", "One of the last 32X releases", "BlueSky Software", "Sega", ["Sega 32X"], "action platformer", None, None, None, None, "Standalone"),
    ("Spider-Man: The Sinister Six", 1996, None, "Standalone", "PC CD-ROM point-and-click", "Brooklyn Multimedia", "Byron Preiss Multimedia", ["MS-DOS"], "point-and-click adventure", None, None, None, None, "Standalone"),
    ("Spider-Man (2000 video game)", 2000, "2000-08-30", "Standalone", "First Activision-era Spider-Man", "Neversoft (PS); Vicarious Visions (GBC); Edge of Reality (N64); Treyarch (DC); LTI Gray Matter (Win)", "Activision", ["PlayStation", "Game Boy Color", "Nintendo 64", "Dreamcast", "Microsoft Windows"], "action-adventure/platformer", None, None, "87 (PS)", "T", "Standalone"),
    ("Spider-Man 2: The Sinister Six", 2001, None, "Standalone", "Handheld sequel", "Torus Games", "Activision", ["Game Boy Color"], "action platformer", None, None, None, None, "Standalone"),
    ("Spider-Man 2: Enter: Electro", 2001, "2001-08-19", "Standalone", "Sequel to the 2000 game", "Vicarious Visions", "Activision", ["PlayStation"], "action-adventure/platformer", None, None, None, "E", "Standalone"),
    ("Spider-Man: Mysterio's Menace", 2001, "2001-09-19", "Standalone", "", "Vicarious Visions", "Activision", ["Game Boy Advance"], "action platformer", None, None, None, "E", "Standalone"),
    ("Spider-Man (2002 video game)", 2002, "2002-04-16", "Movie tie-in", "Tie-in to Spider-Man (2002 film)", "Treyarch; LTI Gray Matter (Win); Digital Eclipse (GBA)", "Activision", ["GameCube", "PlayStation 2", "Xbox", "Microsoft Windows", "Game Boy Advance"], "action-adventure", None, None, "77 (PS2)", "T", "Movie tie-in"),
    ("Spider-Man 2 (2004 video game)", 2004, "2004-06-28", "Movie tie-in", "Tie-in to Spider-Man 2 (2004 film); first open-world web-swinging", "Treyarch; Digital Eclipse (GBA/N-Gage); Foundation 9 (Win); Aspyr (Mac); Vicarious Visions (DS/PSP)", "Activision", ["GameCube", "PlayStation 2", "Xbox", "Windows", "N-Gage", "Mac OS X", "Nintendo DS", "PSP", "Game Boy Advance"], "open world action-adventure", None, None, "83 (PS2); 80 (GC); 82 (Xbox)", "T", "Movie tie-in"),
    ("Ultimate Spider-Man (2005 video game)", 2005, "2005-09-22", "Standalone", "Based on Ultimate Spider-Man comic; cel-shaded art", "Treyarch; Beenox (Win); Vicarious Visions (DS/GBA)", "Activision", ["GameCube", "PlayStation 2", "Xbox", "Windows", "Nintendo DS", "Game Boy Advance"], "open world action-adventure", None, None, "76 (PS2); 75 (GC); 79 (Xbox)", "T", "Standalone"),
    ("Spider-Man: Battle for New York", 2006, "2006-11-07", "Standalone", "", "Torus Games", "Activision", ["Nintendo DS", "Game Boy Advance", "Mobile"], "action beat 'em up", None, None, None, "E10+", "Standalone"),
    ("Spider-Man 3 (2007 video game)", 2007, "2007-05-04", "Movie tie-in", "Tie-in to Spider-Man 3 (2007 film)", "Vicarious Visions; Treyarch (X360/PS3); Beenox (Win)", "Activision", ["Game Boy Advance", "Windows", "Nintendo DS", "PlayStation 2", "Wii", "Xbox 360", "PlayStation 3", "PSP"], "open world action-adventure", None, None, "57 (PS3); 54 (X360); 69 (Wii)", "T", "Movie tie-in"),
    ("Spider-Man: Friend or Foe", 2007, "2007-10-02", "Movie tie-in", "Loosely ties to the film trilogy", "Next Level Games; Beenox (Win); Behaviour Interactive (DS/PSP)", "Activision", ["Windows", "Nintendo DS", "PlayStation 2", "Wii", "Xbox 360", "PSP"], "action beat 'em up", None, None, "61 (X360)", "E10+", "Movie tie-in"),
    ("Spider-Man: Web of Shadows", 2008, "2008-10-21", "Standalone", "Multiple endings based on red/black suit choices", "Shaba Games; Treyarch; Griptonite (DS); Amaze (PS2/PSP)", "Activision", ["Windows", "Nintendo DS", "PlayStation 2", "PlayStation 3", "PSP", "Wii", "Xbox 360"], "open world action-adventure", None, None, "78 (X360); 77 (PS3)", "T", "Standalone"),
    ("Ultimate Spider-Man: Total Mayhem", 2010, "2010-09-22", "Standalone", "Mobile title", "Gameloft", "Gameloft", ["iOS", "Android"], "action beat 'em up", None, None, None, None, "Standalone"),
    ("Spider-Man: Shattered Dimensions", 2010, "2010-09-07", "Standalone", "Four Spider-Men across dimensions (Amazing, Noir, 2099, Ultimate)", "Beenox; Griptonite (DS)", "Activision", ["Nintendo DS", "PlayStation 3", "Wii", "Xbox 360", "Windows"], "action-adventure", None, None, "76 (X360); 76 (PS3)", "T", "Standalone"),
    ("Spider-Man: Edge of Time", 2011, "2011-10-04", "Standalone", "Amazing and 2099 Spider-Men", "Beenox; Other Ocean (DS)", "Activision", ["Nintendo 3DS", "Nintendo DS", "PlayStation 3", "Wii", "Xbox 360"], "action-adventure", None, None, "64 (X360); 65 (PS3)", "T", "Standalone"),
    ("The Amazing Spider-Man (2012 video game)", 2012, "2012-06-26", "Movie tie-in", "Tie-in to The Amazing Spider-Man (2012 film)", "Beenox; Other Ocean (DS); Gameloft (mobile); Mercenary Technology (Vita)", "Activision", ["Nintendo 3DS", "Nintendo DS", "PlayStation 3", "Wii", "Xbox 360", "Android", "iOS", "Windows", "Wii U", "Windows Phone", "PlayStation Vita"], "open world action-adventure", None, None, "64 (X360); 64 (PS3)", "T", "Movie tie-in"),
    ("The Amazing Spider-Man 2 (2014 video game)", 2014, "2014-04-29", "Movie tie-in", "Tie-in to The Amazing Spider-Man 2 (2014 film); last Activision Spider-Man game", "Beenox; Gameloft (mobile); High Voltage (3DS)", "Activision", ["Android", "iOS", "Windows", "Nintendo 3DS", "PlayStation 3", "PlayStation 4", "Wii U", "Xbox 360", "Xbox One"], "open world action-adventure", None, None, "50 (PS4); 50 (XOne)", "T", "Movie tie-in"),
    ("Spider-Man Unlimited (2014 video game)", 2014, "2014-09-10", "Standalone", "Mobile endless runner; shut down 2019", "Gameloft", "Gameloft", ["iOS", "Android", "Windows Phone"], "endless runner", None, None, None, None, "Standalone"),
    ("LEGO Marvel Super Heroes", 2013, "2013-10-22", "LEGO Marvel crossover", "Spider-Man as major playable character", "TT Games", "Warner Bros. Interactive Entertainment", ["PlayStation 3", "PlayStation 4", "Xbox 360", "Xbox One", "Wii U", "Windows", "Nintendo DS", "Nintendo 3DS", "PlayStation Vita", "OS X"], "action-adventure", None, None, "85 (X360)", "E10+", "LEGO Marvel crossover"),
    ("LEGO Marvel Super Heroes 2", 2017, "2017-11-14", "LEGO Marvel crossover", "Spider-Man as major playable character", "TT Games", "Warner Bros. Interactive Entertainment", ["PlayStation 4", "Xbox One", "Nintendo Switch", "Windows"], "action-adventure", None, None, "80 (PS4); 80 (XOne)", "E10+", "LEGO Marvel crossover"),
    ("Marvel's Spider-Man", 2018, "2018-09-07", "Insomniac Spider-Man universe", "Earth-1048; Remastered on PS5 Nov 12 2020 and Windows Aug 12 2022", "Insomniac Games", "Sony Interactive Entertainment", ["PlayStation 4", "PlayStation 5", "Microsoft Windows"], "action-adventure/open world", "Insomniac engine", "Ryan Smith; Brian Horton; Bryan Intihar; Marcus Smith", "87 (PS4)", "T", "Insomniac Spider-Man universe"),
    ("Marvel's Spider-Man: The City That Never Sleeps", 2018, "2018-10-23", "Insomniac Spider-Man universe", "3-episode DLC for Marvel's Spider-Man", "Insomniac Games", "Sony Interactive Entertainment", ["PlayStation 4"], "action-adventure (DLC)", None, None, None, "T", "Insomniac Spider-Man universe"),
    ("Marvel's Spider-Man Remastered", 2020, "2020-11-12", "Insomniac Spider-Man universe", "Remaster with ray tracing, new Peter model", "Insomniac Games; Nixxes Software (PC)", "Sony Interactive Entertainment", ["PlayStation 5", "Microsoft Windows"], "action-adventure/open world", None, None, "87 (base)", "T", "Insomniac Spider-Man universe"),
    ("Marvel's Spider-Man: Miles Morales", 2020, "2020-11-12", "Insomniac Spider-Man universe", "Spin-off; PC release Nov 18 2022", "Insomniac Games; Nixxes Software (PC)", "Sony Interactive Entertainment", ["PlayStation 4", "PlayStation 5", "Microsoft Windows"], "action-adventure/open world", None, "Brian Horton; Cameron Christian", "85 (PS5)", "T", "Insomniac Spider-Man universe"),
    ("Marvel's Spider-Man 2", 2023, "2023-10-20", "Insomniac Spider-Man universe", "PC release Jan 30 2025; features Venom symbiote", "Insomniac Games; Nixxes Software (PC)", "Sony Interactive Entertainment", ["PlayStation 5", "Microsoft Windows"], "action-adventure/open world", None, "Bryan Intihar; Ryan Smith", "90 (PS5)", "T", "Insomniac Spider-Man universe"),
    ("Marvel's Spider-Man 3", None, None, "Insomniac Spider-Man universe", "In development; internal target 2028 (per leaked roadmap); not officially released", "Insomniac Games", "Sony Interactive Entertainment", ["PlayStation 5"], "action-adventure/open world", None, None, None, "T", "Insomniac Spider-Man universe"),
]

for row in games_data:
    (title, year, date, franch, notes, dev, pub, platforms, genre, engine, directors, meta, esrb, universe) = row
    wid = add_work(title, year, date, "game", franch, notes)
    cur.execute("""INSERT INTO games(work_id, developer, publisher, genre, engine, directors,
                     metacritic_score, esrb_rating, universe, notes)
                     VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (wid, dev, pub, genre, engine, directors, meta, esrb, universe, notes))
    for p in platforms:
        cur.execute("INSERT OR IGNORE INTO platforms(name) VALUES (?)", (p,))
        pid = cur.execute("SELECT id FROM platforms WHERE name=?", (p,)).fetchone()[0]
        cur.execute("INSERT OR IGNORE INTO game_platforms(game_id, platform_id) VALUES (?,?)", (wid, pid))

# ---------------------------------------------------------------------------
# PEOPLE & ROLES
# ---------------------------------------------------------------------------
# Pull spider-man actors / voice actors into a people table for rich linking.
actor_roles = []  # (work_title, person, role)
for row in movies_data:
    title = row[0]; actor = row[15]
    if actor:
        # strip parenthetical detail for person name
        name = actor.split(" (")[0]
        actor_roles.append((title, name, "spider-man actor"))
for row in tv_data:
    title = row[0]; voice = row[14]
    if voice:
        for nm in voice.split(";"):
            nm = nm.strip()
            # take first parenthetical-free part
            nm = nm.split(" (")[0].strip()
            if nm:
                actor_roles.append((title, nm, "spider-man actor"))

# Add a few directors/writers for richness
extra = [
    ("Spider-Man", 2002, "Sam Raimi", "director"),
    ("Spider-Man 2", 2004, "Sam Raimi", "director"),
    ("Spider-Man 3", 2007, "Sam Raimi", "director"),
    ("Spider-Man: Homecoming", 2017, "Jon Watts", "director"),
    ("Spider-Man: Into the Spider-Verse", 2018, "Phil Lord", "writer"),
    ("Spider-Man: Into the Spider-Verse", 2018, "Christopher Miller", "producer"),
    ("Marvel's Spider-Man", 2018, "Bryan Intihar", "game director"),
    ("Marvel's Spider-Man 2", 2023, "Bryan Intihar", "game director"),
]

for title, year, person, role in [(r[0], None, r[1], r[2]) for r in actor_roles] + [
    (e[0], e[1], e[2], e[3]) for e in extra
]:
    # find work by title (and year if given)
    if year is not None:
        row = cur.execute("SELECT id FROM media_works WHERE title=? AND release_year=?", (title, year)).fetchone()
    else:
        row = cur.execute("SELECT id FROM media_works WHERE title=?", (title,)).fetchone()
    if not row:
        continue
    wid = row[0]
    cur.execute("INSERT OR IGNORE INTO people(name) VALUES (?)", (person,))
    pid = cur.execute("SELECT id FROM people WHERE name=?", (person,)).fetchone()[0]
    cur.execute("INSERT OR IGNORE INTO work_people(work_id, person_id, role) VALUES (?,?,?)", (wid, pid, role))

conn.commit()

# ---------------------------------------------------------------------------
# CSV EXPORT
# ---------------------------------------------------------------------------
def dump_table(table, path):
    cols = [r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]
    rows = cur.execute(f"SELECT * FROM {table}").fetchall()
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)
    return len(rows)

csv_counts = {}
csv_counts["media_works"] = dump_table("media_works", os.path.join(DATA, "media_works.csv"))
csv_counts["movies"] = dump_table("movies", os.path.join(DATA, "movies.csv"))
csv_counts["tv_shows"] = dump_table("tv_shows", os.path.join(DATA, "tv_shows.csv"))
csv_counts["games"] = dump_table("games", os.path.join(DATA, "games.csv"))
csv_counts["platforms"] = dump_table("platforms", os.path.join(DATA, "platforms.csv"))
csv_counts["game_platforms"] = dump_table("game_platforms", os.path.join(DATA, "game_platforms.csv"))
csv_counts["franchises"] = dump_table("franchises", os.path.join(DATA, "franchises.csv"))
csv_counts["people"] = dump_table("people", os.path.join(DATA, "people.csv"))
csv_counts["work_people"] = dump_table("work_people", os.path.join(DATA, "work_people.csv"))

# Flat combined CSV: one row per media work with its detail columns concatenated.
flat_path = os.path.join(DATA, "spiderman_all_media_flat.csv")
with open(flat_path, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow([
        "id", "title", "release_year", "release_date", "media_type", "franchise",
        # movie fields
        "sub_type", "studio", "distributor", "director", "writer", "producer",
        "runtime_minutes", "mpaa_rating", "budget_usd", "box_office_worldwide_usd",
        "spider_man_actor", "rotten_tomatoes_score", "metacritic_score", "imdb_score",
        # tv fields
        "format", "network", "start_year", "end_year", "seasons", "episodes",
        "head_writer", "tv_director", "voice_actor_spider_man", "status",
        # game fields
        "developer", "publisher", "genre", "engine", "game_directors",
        "game_metacritic_score", "esrb_rating", "game_universe", "game_notes",
        "notes",
    ])
    for mw in cur.execute("SELECT * FROM media_works ORDER BY media_type, release_year, title").fetchall():
        wid, title, year, date, mtype, fid, notes = mw
        franch = cur.execute("SELECT name FROM franchises WHERE id=?", (fid,)).fetchone()[0]
        row = [wid, title, year, date, mtype, franch]
        if mtype == "movie":
            m = cur.execute("SELECT sub_type, studio, distributor, director, writer, producer, "
                            "runtime_minutes, mpaa_rating, budget_usd, box_office_worldwide_usd, "
                            "spider_man_actor, rotten_tomatoes_score, metacritic_score, imdb_score "
                            "FROM movies WHERE work_id=?", (wid,)).fetchone()
            row += list(m) + [""] * 10 + [""] * 9
        elif mtype == "tv_show":
            t = cur.execute("SELECT sub_type, format, network, start_year, end_year, seasons, "
                            "episodes, head_writer, director, voice_actor_spider_man, status "
                            "FROM tv_shows WHERE work_id=?", (wid,)).fetchone()
            row += [t[0]] + [""] * 13 + list(t[1:]) + [""] * 9
        elif mtype == "game":
            g = cur.execute("SELECT developer, publisher, genre, engine, directors, "
                            "metacritic_score, esrb_rating, universe, notes FROM games WHERE work_id=?", (wid,)).fetchone()
            row += [""] + [""] * 13 + [""] * 10 + list(g)
        row.append(notes)
        w.writerow(row)

print("Database built at:", DB_PATH)
print("Table row counts:")
for t, n in csv_counts.items():
    print(f"  {t:14s} {n}")
print("Flat CSV:", flat_path)

conn.close()
