from vgrid.utils import s2, olc, geohash, mercantile
from ...utils.resampling import dggsgrid

import h3
import os, re
from vgrid.stats.s2stats import s2_metrics
from vgrid.stats.rhealpixstats import rhealpix_metrics
from vgrid.stats.isea4tstats import isea4t_metrics
from vgrid.stats.qtmstats import qtm_metrics
from vgrid.stats.olcstats import olc_metrics
from vgrid.stats.geohashstats import geohash_metrics
from vgrid.stats.tilecodestats import tilecode_metrics
from vgrid.stats.quadkeystats import quadkey_metrics
from shapely.wkt import loads as load_wkt

from shapely.geometry import shape
from vgrid.generator import h3grid, s2grid, rhealpixgrid, isea4tgrid, qtmgrid, olcgrid, geohashgrid, tilecodegrid, quadkeygrid
from numbers import Number
from vgrid.utils.rhealpixdggs.dggs import RHEALPixDGGS
from vgrid.utils.rhealpixdggs.ellipsoids import WGS84_ELLIPSOID
from pyproj import Geod
import platform
if (platform.system() == 'Windows'):
    from vgrid.utils.eaggr.eaggr import Eaggr
    from vgrid.utils.eaggr.shapes.dggs_cell import DggsCell
    from vgrid.utils.eaggr.enums.model import Model
    from vgrid.utils.eaggr.enums.shape_string_format import ShapeStringFormat
    from vgrid.generator.settings import isea4t_res_accuracy_dict

from qgis.core import (
    QgsFeature,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QVariant
from shapely.wkt import loads as load_wkt
from numbers import Number


geod = Geod(ellps="WGS84")
E = WGS84_ELLIPSOID

def get_nearest_resolution(qgs_features, from_dggs, to_dggs, from_field=None, feedback=None): 
    if not from_field:
        from_field = from_dggs

    try:
        for feature in qgs_features.getFeatures():  # Use getFeatures() to iterate through the features
            from_dggs_id = feature[from_field]
            break
        else:
            raise ValueError("No features provided.")
    except Exception as e:
        if feedback:
            feedback.reportError(f"No valid DGGS IDs found in <{from_field}> field.")
        return

    try:
        if from_dggs == 'h3':
            from_resolution = h3.get_resolution(from_dggs_id)
            from_area = h3.average_hexagon_area(from_resolution, unit='m^2')

        elif from_dggs == 's2':
            s2_id = s2.CellId.from_token(from_dggs_id)
            from_resolution = s2_id.level()
            _, _, from_area = s2_metrics(from_resolution)

        elif from_dggs == 'rhealpix':
            rhealpix_uids = (from_dggs_id[0],) + tuple(map(int, from_dggs_id[1:]))
            rhealpix_dggs = RHEALPixDGGS(ellipsoid=E, north_square=1, south_square=3, N_side=3)
            rhealpix_cell = rhealpix_dggs.cell(rhealpix_uids)
            from_resolution = rhealpix_cell.resolution
            _, _, from_area = rhealpix_metrics(from_resolution)

        elif from_dggs == 'isea4t':
            if platform.system() == 'Windows':
                from_resolution = len(from_dggs_id) - 2
                isea4t_dggs = Eaggr(Model.ISEA4T)
                _, _, from_area, _ = isea4t_metrics(isea4t_dggs, from_resolution)

        elif from_dggs == 'qtm':
            from_resolution = len(from_dggs_id)
            _, _, from_area = qtm_metrics(from_resolution)

        elif from_dggs == 'olc':
            coord = olc.decode(from_dggs_id)
            from_resolution = coord.codeLength
            _, _, from_area = olc_metrics(from_resolution)

        elif from_dggs == 'geohash':
            from_resolution = len(from_dggs_id)
            _, _, from_area = geohash_metrics(from_resolution)

        elif from_dggs == 'tilecode':
            match = re.match(r'z(\d+)x(\d+)y(\d+)', from_dggs_id)
            from_resolution = int(match.group(1))
            _, _, from_area = tilecode_metrics(from_resolution)

        elif from_dggs == 'quadkey':
            tile = mercantile.quadkey_to_tile(from_dggs_id)
            from_resolution = tile.z
            _, _, from_area = quadkey_metrics(from_resolution)

    except Exception as e:
        if feedback:
            feedback.reportError(f"Failed to calculate area from {from_dggs}: {str(e)}")
        return

    nearest_resolution = None
    min_diff = float('inf')

    try:
        if to_dggs == 'h3':
            for res in range(16):
                avg_area = h3.average_hexagon_area(res, unit='m^2')
                diff = abs(avg_area - from_area)
                if diff < min_diff:
                    min_diff = diff
                    nearest_resolution = res

        elif to_dggs == 's2':
            for res in range(31):
                _, _, avg_area = s2_metrics(res)
                diff = abs(avg_area - from_area)
                if diff < min_diff:
                    min_diff = diff
                    nearest_resolution = res

        elif to_dggs == 'rhealpix':
            for res in range(16):
                _, _, avg_area = rhealpix_metrics(res)
                diff = abs(avg_area - from_area)
                if diff < min_diff:
                    min_diff = diff
                    nearest_resolution = res

        elif to_dggs == 'isea4t':
            if platform.system() == 'Windows':
                isea4t_dggs = Eaggr(Model.ISEA4T)
                for res in range(26):
                    _, _, avg_area, _ = isea4t_metrics(isea4t_dggs, res)
                    diff = abs(avg_area - from_area)
                    if diff < min_diff:
                        min_diff = diff
                        nearest_resolution = res

        elif to_dggs == 'qtm':
            for res in range(1, 25):
                _, _, avg_area = qtm_metrics(res)
                diff = abs(avg_area - from_area)
                if diff < min_diff:
                    min_diff = diff
                    nearest_resolution = res

        elif to_dggs == 'olc':
            for res in [2, 4, 6, 8, 10, 11, 12, 13, 14, 15]:
                _, _, avg_area = olc_metrics(res)
                diff = abs(avg_area - from_area)
                if diff < min_diff:
                    min_diff = diff
                    nearest_resolution = res

        elif to_dggs == 'geohash':
            for res in range(1, 11):
                _, _, avg_area = geohash_metrics(res)
                diff = abs(avg_area - from_area)
                if diff < min_diff:
                    min_diff = diff
                    nearest_resolution = res

        elif to_dggs == 'tilecode':
            for res in range(30):
                _, _, avg_area = tilecode_metrics(res)
                diff = abs(avg_area - from_area)
                if diff < min_diff:
                    min_diff = diff
                    nearest_resolution = res

        elif to_dggs == 'quadkey':
            for res in range(30):
                _, _, avg_area = quadkey_metrics(res)
                diff = abs(avg_area - from_area)
                if diff < min_diff:
                    min_diff = diff
                    nearest_resolution = res

    except Exception as e:
        if feedback:
            feedback.reportError(f"Failed to calculate nearest resolution for {to_dggs}: {str(e)}")
        return

    if feedback:
        feedback.pushInfo(f"Nearest {to_dggs} resolution: {nearest_resolution}")
    return nearest_resolution

def generate_grid(qgs_features, to_dggs, resolution, feedback=None):
    dggs_grid = {}
    if to_dggs == 'h3':
        dggs_grid = dggsgrid.generate_h3_grid(resolution, qgs_features, feedback)
    elif to_dggs == 's2':
        dggs_grid = dggsgrid.generate_s2_grid(resolution, qgs_features,feedback)
    elif to_dggs == 'rhealpix':
        rhealpix_dggs = RHEALPixDGGS()
        dggs_grid = dggsgrid.generate_rhealpix_grid(rhealpix_dggs,resolution, qgs_features,feedback)
    elif to_dggs == 'isea4t':
        if (platform.system() == 'Windows'): 
            isea4t_dggs = Eaggr(Model.ISEA4T)
            dggs_grid = dggsgrid.generate_isea4t_grid(isea4t_dggs,resolution, qgs_features,feedback)
    elif to_dggs == 'qtm':
        dggs_grid = dggsgrid.generate_qtm_grid(resolution, qgs_features,feedback)
    elif to_dggs == 'olc':
        dggs_grid = dggsgrid.generate_olc_grid(resolution, qgs_features,feedback)
    elif to_dggs == 'geohash':
        dggs_grid = dggsgrid.generate_geohash_grid(resolution, qgs_features,feedback)
    elif to_dggs == 'tilecode':
        dggs_grid = dggsgrid.generate_tilecode_grid(resolution, qgs_features,feedback)
    elif to_dggs == 'quadkey':
        dggs_grid = dggsgrid.generate_quadkey_grid(resolution, qgs_features,feedback)
    else:
        raise ValueError(f"Unsupported DGGS type: {to_dggs}")

    return dggs_grid

def resampling(layer1, layer2, resample_field, feedback=None):
    try:
        layer1_features = []
        for feature in layer1.getFeatures():
            if resample_field not in feature.fields().names():
                raise ValueError(f"There is no <{resample_field}> field in the input layer1 features.")
            geom = load_wkt(feature.geometry().asWkt())
            value = feature[resample_field]
            layer1_features.append((geom, value))
    except ValueError as e:
        if feedback:
            feedback.reportError(str(e))
        else:
            print(e)
        return layer2

    # Prepare output layer with same geometry and attributes + resample_field
    fields = layer2.fields()
    if resample_field not in fields.names():
        fields.append(QgsField(resample_field, QVariant.Double))

    output_layer = QgsVectorLayer("Polygon?crs=" + layer2.crs().authid(), "resampled", "memory")
    output_layer.startEditing()
    output_layer.dataProvider().addAttributes(fields)
    output_layer.updateFields()

    total = layer2.featureCount()
    resampled_count = 0

    if feedback:
        feedback.pushInfo(f"Starting resampling on {total} features...")

    for i, feature in enumerate(layer2.getFeatures()):
        if feedback and feedback.isCanceled():
            feedback.reportError("Operation cancelled.")
            return output_layer

        layer2_geom = load_wkt(feature.geometry().asWkt())
        resampled_value = 0.0
        intersected_parts = []

        for l1_geom, l1_value in layer1_features:
            if layer2_geom.intersects(l1_geom):
                if not isinstance(l1_value, Number):
                    msg = f"Non-numeric value found in <{resample_field}>. Resampled field calculation failed."
                    if feedback:
                        feedback.reportError(msg)
                    return output_layer

                intersection = layer2_geom.intersection(l1_geom)
                if not intersection.is_empty:
                    proportion = intersection.area / l1_geom.area
                    resampled_value += l1_value * proportion
                    intersected_parts.append(intersection)

        if not intersected_parts:
            continue

        new_feat = QgsFeature(fields)
        new_feat.setGeometry(QgsGeometry.fromWkt(layer2_geom.wkt))
        attrs = list(feature.attributes())
        if len(attrs) < fields.count():
            attrs.append(round(resampled_value, 3))
        else:
            idx = fields.indexOf(resample_field)
            attrs[idx] = round(resampled_value, 3)
        new_feat.setAttributes(attrs)

        output_layer.addFeature(new_feat)
        resampled_count += 1

        if feedback:
            feedback.setProgress(int((i + 1) / total * 100))

    output_layer.commitChanges()
    output_layer.updateExtents()

    if feedback:
        feedback.setProgress(100)
        feedback.pushInfo(f"Resampling complete. {resampled_count} features updated.")

    return output_layer

def resample(dggs_layer, dggstype_from, dggstype_to, resolution, dggs_field=None, resample_field=None, feedback=None):
    resampled_features = None
    if resolution == -1:
        resolution = get_nearest_resolution(dggs_layer, dggstype_from, dggstype_to,dggs_field)
        if feedback:
            feedback.pushInfo(f"Nearest resolution: {resolution}")
    if resolution:
        resampled_features = generate_grid(dggs_layer, dggstype_to, resolution, feedback)
        if resample_field: 
            resampled_features = resampling(dggs_layer, resampled_features,resample_field, feedback)
    return resampled_features