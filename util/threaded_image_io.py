import concurrent.futures as futures
import freeimage

class ThreadedIO:
    def __init__(self, num_threads):
        self.threadpool = futures.ThreadPoolExecutor(num_threads)

    def write(self, images, paths, flags=0):
        """Write out a list of images to the given paths."""
        futures_out = [self.threadpool.submit(freeimage.write, image, str(path), flags) for image, path in zip(images, paths)]
        futures.wait(futures_out)

    def read(self, paths):
        """Return an iterator over image arrays read from the given paths."""
        paths = map(str, paths)
        return self.threadpool.map(freeimage.read, paths)
