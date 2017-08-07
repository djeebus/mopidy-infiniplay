import logging
import pkg_resources
import pykka
import random

from mopidy.core import CoreListener
from mopidy.core.actor import Core
from mopidy.ext import Extension

__version__ = '0.1.4'
logger = logging.getLogger('mopidy-infiniplay')


class InfiniPlayController(pykka.ThreadingActor, CoreListener):
    """Keeps the music going! If the music has stopped for n seconds, play
    a random song."""

    max_quiet_time = 1.5
    max_empty_time = 1.5

    def __init__(self, config, core):
        pykka.ThreadingActor.__init__(self)
        self.config = config
        self.core = core  # type: Core

        self._is_adding = False
        self._tracklist = []

    def on_start(self):
        self._configure_mopidy()
        self._build_tracklist()

        self._check_state()

    def track_playback_ended(self, tl_track, time_position):
        # when adding a track, the previous track stops, which triggers this
        # event. ignore it.
        if self._is_adding:
            return

        self._check_state()

    def _configure_mopidy(self):
        tracklist = self.core.tracklist

        tracklist.set_consume(True).get()
        tracklist.set_random(False).get()
        tracklist.set_repeat(False).get()
        tracklist.set_single(False).get()

    def _check_state(self):
        tracklist = self.core.tracklist
        next_track_id = tracklist.get_eot_tlid().get()
        if next_track_id:
            logger.info('a song was manually added, not playing a new track')
            return

        self._play_random_track()

    def _build_tracklist(self):
        logger.info('configurating tracklist')

        library = self.core.library

        completed_work = set()
        work = library.browse(None).get()
        while work:
            item = work.pop()
            uri = item.uri
            if uri in completed_work:
                continue

            if not uri.startswith('local:'):
                continue

            item_type = item.type
            if item_type == 'directory':
                new_work = library.browse(uri=uri).get()
                work += new_work
            elif item_type == 'track':
                self._tracklist.append(uri)
            else:
                print("--- unknown type: %s ---" % item_type)
                # tracklist.add(uri=uri)

            completed_work.add(uri)

        logger.info('found %s tracks' % len(self._tracklist))

    def _play_random_track(self):
        if not self._tracklist:
            logger.warning('no tracks to shuffle!')
            return

        track_uri = random.choice(self._tracklist)

        logger.info('playing %s' % track_uri)

        tracklist = self.core.tracklist

        self._is_adding = True
        items = tracklist.add(uri=track_uri).get()
        self._is_adding = False

        # assumption: new item is always at the end
        item = items[-1]

        playback = self.core.playback
        playback.play(tlid=item.tlid).get()

    def _initialize_playlist(self):
        library = self.core.library

        uris_to_add = list()
        completed_work = set()
        work = library.browse(None).get()
        while work:
            item = work.pop()
            uri = item.uri
            if uri in completed_work:
                continue

            if not uri.startswith('local:'):
                continue

            item_type = item.type
            if item_type == 'directory':
                new_work = library.browse(uri=uri).get()
                work += new_work
            elif item_type == 'track':
                uris_to_add.append(uri)

            completed_work.add(uri)

        tracklist = self.core.tracklist
        tracklist.set_random(True)
        tracklist.set_repeat(True)

        tracklist.set_consume(False)
        tracklist.set_single(False)

        tracklist.add(uris=uris_to_add).get()


class InfiniPlayExtension(Extension):
    dist_name = 'Mopidy-InfiniPlay'
    ext_name = 'infiniplay'
    version = __version__

    def get_default_config(self):
        fp = pkg_resources.resource_stream('mopidy_infiniplay', 'ext.conf')
        with fp:
            return fp.read()

    def setup(self, registry):
        registry.add('frontend', InfiniPlayController)
