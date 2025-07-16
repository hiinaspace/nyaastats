import json
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from nyaastats.database import Database


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    db = Database(db_path)
    yield db
    
    # Cleanup
    Path(db_path).unlink(missing_ok=True)


def test_database_init(temp_db):
    """Test database initialization."""
    # Check that tables exist
    with temp_db.get_conn() as conn:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        assert 'torrents' in tables
        assert 'stats' in tables


def test_database_schema(temp_db):
    """Test database schema is correct."""
    with temp_db.get_conn() as conn:
        # Check torrents table structure
        cursor = conn.execute("PRAGMA table_info(torrents)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        
        expected_columns = {
            'infohash': 'TEXT',
            'filename': 'TEXT',
            'pubdate': 'TIMESTAMP',
            'size_bytes': 'INTEGER',
            'nyaa_id': 'INTEGER',
            'trusted': 'BOOLEAN',
            'remake': 'BOOLEAN',
            'status': 'TEXT',
            'title': 'TEXT',
            'episode': 'INTEGER',
            'season': 'INTEGER',
            'year': 'INTEGER',
            'release_group': 'TEXT',
            'resolution': 'TEXT',
            'video_codec': 'TEXT',
            'audio_codec': 'TEXT',
            'source': 'TEXT',
            'container': 'TEXT',
            'language': 'TEXT',
            'subtitles': 'TEXT',
            'other': 'TEXT'
        }
        
        for col, col_type in expected_columns.items():
            assert col in columns
            assert columns[col] == col_type


def test_insert_torrent(temp_db):
    """Test inserting a torrent."""
    torrent_data = {
        'infohash': 'abcdef1234567890abcdef1234567890abcdef12',
        'filename': '[Test] Anime Episode 01 [1080p].mkv',
        'pubdate': datetime(2023, 1, 1, 12, 0, 0),
        'size_bytes': 1000000000,
        'nyaa_id': 12345,
        'trusted': True,
        'remake': False,
        'seeders': 10,
        'leechers': 2,
        'downloads': 100
    }
    
    guessit_data = {
        'title': 'Anime',
        'episode': 1,
        'resolution': '1080p',
        'container': 'mkv',
        'release_group': 'Test',
        'video_codec': 'H.264',
        'audio_codec': 'AAC',
        'source': 'BluRay',
        'language': 'en',
        'subtitles': ['en', 'jp'],
        'custom_field': 'custom_value'  # This will go into "other"
    }
    
    temp_db.insert_torrent(torrent_data, guessit_data)
    
    # Verify torrent was inserted
    with temp_db.get_conn() as conn:
        cursor = conn.execute("SELECT * FROM torrents WHERE infohash = ?", (torrent_data['infohash'],))
        row = cursor.fetchone()
        
        assert row is not None
        assert row['infohash'] == torrent_data['infohash']
        assert row['filename'] == torrent_data['filename']
        assert row['size_bytes'] == torrent_data['size_bytes']
        assert row['nyaa_id'] == torrent_data['nyaa_id']
        assert row['trusted'] == torrent_data['trusted']
        assert row['remake'] == torrent_data['remake']
        assert row['title'] == guessit_data['title']
        assert row['episode'] == guessit_data['episode']
        assert row['resolution'] == guessit_data['resolution']
        assert row['container'] == guessit_data['container']
        assert row['release_group'] == guessit_data['release_group']
        assert row['video_codec'] == guessit_data['video_codec']
        assert row['audio_codec'] == guessit_data['audio_codec']
        assert row['source'] == guessit_data['source']
        assert row['language'] == guessit_data['language']
        assert json.loads(row['subtitles']) == guessit_data['subtitles']
        assert json.loads(row['other']) == {'custom_field': 'custom_value'}
        
        # Verify initial stats were inserted
        cursor = conn.execute("SELECT * FROM stats WHERE infohash = ?", (torrent_data['infohash'],))
        stats_row = cursor.fetchone()
        
        assert stats_row is not None
        assert stats_row['seeders'] == torrent_data['seeders']
        assert stats_row['leechers'] == torrent_data['leechers']
        assert stats_row['downloads'] == torrent_data['downloads']


def test_insert_stats(temp_db):
    """Test inserting statistics."""
    infohash = 'abcdef1234567890abcdef1234567890abcdef12'
    stats = {'seeders': 5, 'leechers': 1, 'downloads': 50}
    timestamp = datetime(2023, 1, 2, 12, 0, 0)
    
    temp_db.insert_stats(infohash, stats, timestamp)
    
    with temp_db.get_conn() as conn:
        cursor = conn.execute("SELECT * FROM stats WHERE infohash = ?", (infohash,))
        row = cursor.fetchone()
        
        assert row is not None
        assert row['infohash'] == infohash
        assert row['seeders'] == stats['seeders']
        assert row['leechers'] == stats['leechers']
        assert row['downloads'] == stats['downloads']


def test_mark_torrent_status(temp_db):
    """Test marking torrent status."""
    # First insert a torrent
    torrent_data = {
        'infohash': 'abcdef1234567890abcdef1234567890abcdef12',
        'filename': '[Test] Anime Episode 01 [1080p].mkv',
        'pubdate': datetime(2023, 1, 1, 12, 0, 0),
        'size_bytes': 1000000000,
        'nyaa_id': 12345,
        'trusted': True,
        'remake': False,
        'seeders': 10,
        'leechers': 2,
        'downloads': 100
    }
    
    temp_db.insert_torrent(torrent_data, {})
    
    # Mark as dead
    temp_db.mark_torrent_status(torrent_data['infohash'], 'dead')
    
    with temp_db.get_conn() as conn:
        cursor = conn.execute("SELECT status FROM torrents WHERE infohash = ?", (torrent_data['infohash'],))
        row = cursor.fetchone()
        
        assert row is not None
        assert row['status'] == 'dead'


def test_get_torrent_exists(temp_db):
    """Test checking if torrent exists."""
    infohash = 'abcdef1234567890abcdef1234567890abcdef12'
    
    # Should not exist initially
    assert not temp_db.get_torrent_exists(infohash)
    
    # Insert a torrent
    torrent_data = {
        'infohash': infohash,
        'filename': '[Test] Anime Episode 01 [1080p].mkv',
        'pubdate': datetime(2023, 1, 1, 12, 0, 0),
        'size_bytes': 1000000000,
        'nyaa_id': 12345,
        'trusted': True,
        'remake': False,
        'seeders': 10,
        'leechers': 2,
        'downloads': 100
    }
    
    temp_db.insert_torrent(torrent_data, {})
    
    # Should exist now
    assert temp_db.get_torrent_exists(infohash)


def test_get_recent_stats(temp_db):
    """Test getting recent statistics."""
    infohash = 'abcdef1234567890abcdef1234567890abcdef12'
    
    # Insert multiple stats
    stats_data = [
        ({'seeders': 10, 'leechers': 2, 'downloads': 100}, datetime(2023, 1, 1, 12, 0, 0)),
        ({'seeders': 8, 'leechers': 1, 'downloads': 105}, datetime(2023, 1, 1, 13, 0, 0)),
        ({'seeders': 5, 'leechers': 0, 'downloads': 110}, datetime(2023, 1, 1, 14, 0, 0)),
        ({'seeders': 3, 'leechers': 1, 'downloads': 115}, datetime(2023, 1, 1, 15, 0, 0))
    ]
    
    for stats, timestamp in stats_data:
        temp_db.insert_stats(infohash, stats, timestamp)
    
    # Get recent stats (should be in descending order)
    recent = temp_db.get_recent_stats(infohash, limit=3)
    
    assert len(recent) == 3
    assert recent[0]['seeders'] == 3  # Most recent
    assert recent[1]['seeders'] == 5
    assert recent[2]['seeders'] == 8


def test_vacuum(temp_db):
    """Test database vacuum operation."""
    # This should not raise any errors
    temp_db.vacuum()


def test_indexes_exist(temp_db):
    """Test that required indexes exist."""
    with temp_db.get_conn() as conn:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = [row[0] for row in cursor.fetchall()]
        
        expected_indexes = [
            'idx_stats_infohash',
            'idx_stats_timestamp',
            'idx_torrents_pubdate',
            'idx_torrents_status'
        ]
        
        for index in expected_indexes:
            assert index in indexes


def test_insert_duplicate_torrent(temp_db):
    """Test inserting duplicate torrent (should be ignored)."""
    torrent_data = {
        'infohash': 'abcdef1234567890abcdef1234567890abcdef12',
        'filename': '[Test] Anime Episode 01 [1080p].mkv',
        'pubdate': datetime(2023, 1, 1, 12, 0, 0),
        'size_bytes': 1000000000,
        'nyaa_id': 12345,
        'trusted': True,
        'remake': False,
        'seeders': 10,
        'leechers': 2,
        'downloads': 100
    }
    
    # Insert first time
    temp_db.insert_torrent(torrent_data, {'title': 'First'})
    
    # Insert duplicate (should be ignored)
    temp_db.insert_torrent(torrent_data, {'title': 'Second'})
    
    # Check only one record exists
    with temp_db.get_conn() as conn:
        cursor = conn.execute("SELECT COUNT(*) as count FROM torrents WHERE infohash = ?", (torrent_data['infohash'],))
        count = cursor.fetchone()['count']
        
        assert count == 1
        
        # Check the title is still from first insert
        cursor = conn.execute("SELECT title FROM torrents WHERE infohash = ?", (torrent_data['infohash'],))
        row = cursor.fetchone()
        
        assert row['title'] == 'First'