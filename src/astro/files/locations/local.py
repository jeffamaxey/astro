import glob
import pathlib
from typing import Dict, List, Union
from urllib.parse import urlparse

from astro.constants import FileLocation
from astro.files.locations.base import Location


class Local(Location):
    """Handler Local file path operations"""

    location_type = FileLocation.LOCAL

    def get_paths(self) -> List[str]:
        """Resolve local filepath"""
        url = urlparse(self.path)
        path_object = pathlib.Path(url.path)
        if path_object.is_dir():
            paths = [str(filepath) for filepath in path_object.rglob("*")]
        else:
            paths = glob.glob(url.path)
        return paths

    def get_transport_params(self) -> Union[Dict, None]:
        """Dummy method"""
        return None
