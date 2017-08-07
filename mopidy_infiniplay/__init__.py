import mopidy
import mopidy.config
import mopidy.core
import mopidy.ext
import os
import pykka
import sched
import threading
import time

__version__ = '0.1.0'


class PartyController(pykka.ThreadingActor, mopidy.core.CoreListener):
    """Keeps the music going! If the music has stopped for n seconds, play
    a random song."""

    max_quiet_time = 1.5
    max_empty_time = 1.5

    def __init__(self, config, core):
        pykka.ThreadingActor.__init__(self)
        self.config = config
        self.core = core

        self._keep_running = True
        self._stopped_at = time.time()
        self._timer = sched.scheduler(time.time, time.sleep)

        self._check_tracklist()
        self._repeat(1.0, 1, self._check_tracklist)

        self._check_state()
        self._repeat(1.0, 1, self._check_state)

        self.run_thread = threading.Thread(
            name='party monitor',
            target=self._timer.run,
        )

    def _repeat(self, delay, priority, func):
        def schedule():
            self._timer.enter(delay, priority, wrapper, ())

        def wrapper():
            if not self._keep_running:
                return

            try:
                func()
            except Exception as e:
                print('--- error: %s ---' % e)
            finally:
                if self._keep_running:
                    schedule()

        schedule()

    def _check_tracklist(self):
        tracklist = self.core.tracklist
        track_count = tracklist.get_length().get()
        if track_count > 0:
            return

        print('initializing playlist')
        self._initialize_playlist()

    def _check_state(self):
        if self._stopped_at is None:
            return

        now = time.time()
        quiet_time = now - self._stopped_at
        if quiet_time > self.max_quiet_time:
            print('starting playback')
            self._play_random_track()

    def _play_random_track(self):
        playback = self.core.playback
        playback.next()
        playback.play()

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
            else:
                print("--- unknown type: %s ---" % item_type)
                # tracklist.add(uri=uri)

            completed_work.add(uri)

        tracklist = self.core.tracklist
        tracklist.set_random(True)
        tracklist.set_repeat(True)

        tracklist.set_consume(False)
        tracklist.set_single(False)

        tracklist.add(uris=uris_to_add).get()

    def on_start(self):
        self._keep_running = True
        self.run_thread.start()

    def on_stop(self):
        self._keep_running = False
        self._timer.empty()

    def track_playback_started(self, tl_track):
        self._stopped_at = None

    def track_playback_ended(self, tl_track, time_position):
        self._stopped_at = time.time()


class Extension(mopidy.ext.Extension):
    dist_name = 'Mopidy-InfiniPlay'
    ext_name = 'infiniplay'
    version = __version__

    def get_default_config(self):
        conf_file = os.path.join(os.path.dirname(__file__), 'ext.conf')
        return mopidy.config.read(conf_file)

    def setup(self, registry):
        registry.add('frontend', PartyController)
