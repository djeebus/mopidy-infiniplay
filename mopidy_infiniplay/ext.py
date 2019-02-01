import logging
import pkg_resources
import pykka
import random
import threading
import time

from mopidy.audio.constants import PlaybackState
from mopidy.config import Integer
from mopidy.core import CoreListener
from mopidy.core.actor import Core
from mopidy.ext import Extension
from mopidy.models import Ref

from mopidy_infiniplay import __version__

logger = logging.getLogger('mopidy-infiniplay')
CHECK_STATE = 'BUILD_TRACKLIST'


class InfiniPlayController(pykka.ThreadingActor, CoreListener):
    """Keeps the music going! If the music has stopped for n seconds, play
    a random song."""

    def __init__(self, config, core):
        pykka.ThreadingActor.__init__(self)

        self.min_tracks = config['infiniplay']['min_tracks']
        self.core = core  # type: Core

        self._running = True
        self._cache = None
        self._nanny = threading.Thread(
            target=self._run_nanny,
        )
        self._nanny.daemon = True

    def _run_nanny(self):
        while self._running:
            self._add_tracks()
            self._check_state()

            time.sleep(1)

    def on_start(self):
        self._running = True
        self._nanny.start()

        self._check_state()
        self._configure_mopidy()

        build_thread = threading.Thread(
            target=self._build_tracklist,
        )
        build_thread.daemon = True
        build_thread.start()

    def on_stop(self):
        self._running = False
        self._nanny.join()

    def playback_state_changed(self, old_state, new_state):
        self._check_state()

    def track_playback_ended(self, tl_track, time_position):
        self.core.tracklist.remove({'tlid': [tl_track.tlid]}).get()

    def _configure_mopidy(self):
        tracklist = self.core.tracklist

        tracklist.set_random(False).get()
        tracklist.set_repeat(False).get()
        tracklist.set_single(False).get()

    def _check_state(self):
        playback = self.core.playback

        self._add_tracks()

        state = playback.get_state().get()
        if state == PlaybackState.STOPPED:
            playback.play()

    def _add_tracks(self):
        tracklist = self.core.tracklist

        if self._cache:
            selector = self._get_track_from_cache
        else:
            logger.info("tracks have not been indexed yet")
            selector = self._get_track_from_mopidy

        while self._running:
            length = tracklist.get_length().get()
            if length >= self.min_tracks:
                break

            track_uri = selector()
            if not track_uri:
                logger.warning("Could not find tracks to add, sleeping")
                if not length:
                    # no tracks exist, let the nanny pick it up later
                    return

                # some tracks exist, make sure playback starts
                break

            tracklist.add(uris=[track_uri]).get()

    def _get_track_from_cache(self):
        return random.choice(self._cache)

    folder_ref_types = {
        Ref.DIRECTORY,
        Ref.ARTIST,
        Ref.ALBUM,
    }

    def _get_track_from_mopidy(self, url=None):
        items = self.core.library.browse(url).get()

        # omgz. SQLiteLibrary.browse(None) returns a volatile array,
        # critical to its functionality. Modifying this array causes all
        # kinds of issues, and removing the items makes the class completely
        # unusable. Do not ask how long this took to track down.
        # copy the list to avoid this issue
        items = items[:]
        random.shuffle(items)

        while items and self._running:
            item = items.pop()
            uri = item.uri

            if item.type in self.folder_ref_types:
                subitem = self._get_track_from_mopidy(uri)
                if subitem:
                    return subitem

            elif item.type == Ref.TRACK:
                return uri

    def _build_tracklist(self):
        logger.info('precaching tracks')

        completed_work = set()
        tracklist = list()

        # omgz. SQLiteLibrary.browse(None) returns a volatile array,
        # critical to its functionality. Modifying this array causes all
        # kinds of issues, and removing the items makes the class completely
        # unusable. Do not ask how long this took to track down.
        # copy the list to avoid this issue
        work = list()
        work += self.core.library.browse(None).get()

        while work:
            item = work.pop()
            uri = item.uri
            item_type = item.type

            logger.debug('found %s: %s' % (item_type, uri))
            if uri in completed_work:
                continue

            if item_type in self.folder_ref_types:
                new_work = self.core.library.browse(uri=uri).get()
                work += new_work
            elif item_type == Ref.TRACK:
                tracklist.append(uri)

            completed_work.add(uri)

        self._cache = tracklist
        logger.info('found {count} tracks'.format(count=len(self._cache)))


class InfiniPlayExtension(Extension):
    dist_name = 'Mopidy-InfiniPlay'
    ext_name = 'infiniplay'
    version = __version__

    def get_default_config(self):
        fp = pkg_resources.resource_stream('mopidy_infiniplay', 'ext.conf')
        with fp:
            return fp.read()

    def get_config_schema(self):
        base = super(InfiniPlayExtension, self).get_config_schema()
        base['min_tracks'] = Integer()
        return base

    def setup(self, registry):
        registry.add('frontend', InfiniPlayController)
