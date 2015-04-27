import concurrent.futures as futures
import freeimage

class ThreadedIO:
    def __init__(self, num_threads):
        self.threadpool = futures.ThreadPoolExecutor(num_threads)

    def write(self, images, paths, flags=0):
        """Write out a list of images to the given paths."""
        futures_out = [self.threadpool.submit(freeimage.write, image, str(path), flags) for image, path in zip(images, paths)]
        # wait until all have completed or errored out
        futures.wait(futures_out)
        # now get the result() from each future, which will raise any errors encountered
        # during the execution.
        # The futures.wait() call above makes sure that everything that doesn't
        # error out has a chance to finish before we barf an exception.
        [f.result() for f in futures_out]

    def read(self, paths):
        """Return an iterator over image arrays read from the given paths."""
        paths = map(str, paths)
        return self.threadpool.map(freeimage.read, paths)
