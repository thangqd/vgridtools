# -*- coding: utf-8 -*-
"""
isea4t_grid.py
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""
#  Need to be checked and tested

__author__ = 'Thang Quach'
__date__ = '2024-11-20'
__copyright__ = '(L) 2024, Thang Quach'

from qgis.core import (
    QgsApplication,
    QgsProject,
    QgsFeatureSink,
    QgsProcessingLayerPostProcessorInterface,
    QgsProcessingParameterExtent,
    QgsProcessingParameterNumber,
    QgsProcessingException,
    QgsProcessingParameterFeatureSink,
    QgsProcessingAlgorithm,
    QgsFields,
    QgsField,
    QgsFeature,
    QgsGeometry,
    QgsWkbTypes,
    QgsCoordinateReferenceSystem,
    QgsVectorLayer,
    QgsPalLayerSettings, 
    QgsVectorLayerSimpleLabeling
)
from qgis.PyQt.QtGui import QIcon, QColor
from qgis.PyQt.QtCore import QCoreApplication,QSettings,Qt
from qgis.utils import iface
from PyQt5.QtCore import QVariant
import os, random, platform

if (platform.system() == 'Windows'):
    from vgrid.utils.eaggr.eaggr import Eaggr
    from vgrid.utils.eaggr.shapes.dggs_cell import DggsCell
    from vgrid.utils.eaggr.enums.shape_string_format import ShapeStringFormat
    from vgrid.utils.eaggr.enums.model import Model
    from vgrid.generator.isea4tgrid import isea4t_cell_to_polygon,\
                                          get_isea4t_children_cells,get_isea4t_children_cells_within_bbox,\
                                          fix_isea4t_antimeridian_cells
    from vgrid.generator.settings import isea4t_base_cells

    isea4t_dggs = Eaggr(Model.ISEA4T)
    
from ...utils.imgs import Imgs
from shapely.geometry import box
from vgrid.generator.settings import isea4t_res_accuracy_dict, geodesic_dggs_metrics
from vgrid.utils.antimeridian import fix_polygon


class ISEA4TGrid(QgsProcessingAlgorithm):
    EXTENT = 'EXTENT'
    RESOLUTION = 'RESOLUTION'
    OUTPUT = 'OUTPUT'
    
    LOC = QgsApplication.locale()[:2]
   

    def translate(self, string):
        return QCoreApplication.translate('Processing', string)

    def tr(self, *string):
        # Translate to Vietnamese: arg[0] - English (translate), arg[1] - Vietnamese
        if self.LOC == 'vi':
            if len(string) == 2:
                return string[1]
            else:
                return self.translate(string[0])
        else:
            return self.translate(string[0])
    
    def createInstance(self):
        return ISEA4TGrid()

    def name(self):
        return 'grid_isea4t'

    def icon(self):
        return QIcon(os.path.join(os.path.dirname(os.path.dirname(__file__)),  '../images/generator/grid_triangle.svg'))
    
    def displayName(self):
        return self.tr('ISEA4T', 'ISEA4T')

    def group(self):
        return self.tr('Generator', 'Generator')

    def groupId(self):
        return 'grid'

    def tags(self):
        return self.tr('DGGS, grid, ISEA4T, generator').split(',')
    
    txt_en = 'ISEA4T DGGS Generator'
    txt_vi = 'ISEA4T DGGS Generator'
    figure = '../images/tutorial/grid_isea4t.png'

    def shortHelpString(self):
        social_BW = Imgs().social_BW
        footer = '''<div align="center">
                      <img src="'''+ os.path.join(os.path.dirname(os.path.dirname(__file__)), self.figure) +'''">
                    </div>
                    <div align="right">
                      <p align="right">
                      <b>'''+self.tr('Author: Thang Quach', 'Author: Thang Quach')+'''</b>
                      </p>'''+ social_BW + '''
                    </div>
                    '''
        return self.tr(self.txt_en, self.txt_vi) + footer    

    def initAlgorithm(self, config=None):
        param = QgsProcessingParameterExtent(self.EXTENT,
                                             self.tr('Grid extent'),
                                             optional=True
                                            )
        self.addParameter(param)

        param = QgsProcessingParameterNumber(
                    self.RESOLUTION,
                    self.tr('Resolution [0..39]'),
                    QgsProcessingParameterNumber.Integer,
                    defaultValue=1,
                    minValue= 0,
                    maxValue= 39,
                    optional=False)
        self.addParameter(param)


        param = QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                'ISEA4T')
        self.addParameter(param)
                    
    def prepareAlgorithm(self, parameters, context, feedback):
        self.resolution = self.parameterAsInt(parameters, self.RESOLUTION, context)  
        self.grid_extent = self.parameterAsExtent(parameters, self.EXTENT, context)
        if self.resolution > 8 and (self.grid_extent is None or self.grid_extent.isEmpty()):
            feedback.reportError('For performance reason, when resolution is greater than 8, the grid extent must be set.')
            return False
        
        return True
    
    def outputFields(self):
        output_fields = QgsFields() 
        output_fields.append(QgsField("isea4t", QVariant.String))
        output_fields.append(QgsField('resolution', QVariant.Int))
        output_fields.append(QgsField('center_lat', QVariant.Double))
        output_fields.append(QgsField('center_lon', QVariant.Double))
        output_fields.append(QgsField('avg_edge_len', QVariant.Double))
        output_fields.append(QgsField('cell_area', QVariant.Double))

        return output_fields

    def processAlgorithm(self, parameters, context, feedback):        
        fields = self.outputFields()        
        # Output layer initialization
        (sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            fields,
            QgsWkbTypes.Polygon,
            QgsCoordinateReferenceSystem('EPSG:4326')
        )

        if not sink:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT))

        if self.grid_extent is None or self.grid_extent.isEmpty():
            extent_bbox = None
        else:
            extent_bbox = box(self.grid_extent.xMinimum(), self.grid_extent.yMinimum(), 
                            self.grid_extent.xMaximum(), self.grid_extent.yMaximum())              
       
        if (platform.system() == 'Windows'): 
            if extent_bbox:
                accuracy = isea4t_res_accuracy_dict.get(self.resolution)                
                extent_bbox_wkt = extent_bbox.wkt  # Create a bounding box polygon
                shapes = isea4t_dggs.convert_shape_string_to_dggs_shapes(extent_bbox_wkt, ShapeStringFormat.WKT, accuracy)
                shape = shapes[0]
                bbox_cells = shape.get_shape().get_outer_ring().get_cells()
                bounding_cell = isea4t_dggs.get_bounding_dggs_cell(bbox_cells)
                bounding_children = get_isea4t_children_cells_within_bbox(isea4t_dggs, bounding_cell.get_cell_id(), extent_bbox,self.resolution)
                total_bounding_children = len(bounding_children)
                feedback.pushInfo(f"Total cells to be generated: {total_bounding_children}.")
                
                for idx, child in enumerate(bounding_children):
                    progress = int((idx / total_bounding_children) * 100)
                    feedback.setProgress(progress) 
                    
                    isea4t_cell = DggsCell(child)
                    isea4t_id = isea4t_cell.get_cell_id()
                    cell_polygon = isea4t_cell_to_polygon(isea4t_dggs,isea4t_cell)
                    
                    if self.resolution == 0:
                        cell_polygon = fix_polygon(cell_polygon)
                    
                    elif isea4t_id.startswith('00') or isea4t_id.startswith('09') or isea4t_id.startswith('14') or isea4t_id.startswith('04') or isea4t_id.startswith('19'):
                        cell_polygon = fix_isea4t_antimeridian_cells(cell_polygon)
                                                    
                    # if cell_polygon.intersects(extent_bbox):
                    cell_geometry = QgsGeometry.fromWkt(cell_polygon.wkt)            
                    isea4t_feature = QgsFeature()
                    isea4t_feature.setGeometry(cell_geometry)                     
                    
                    num_edges = 3
                    center_lat, center_lon, avg_edge_len, cell_area = geodesic_dggs_metrics(cell_polygon, num_edges)
                    isea4t_feature.setAttributes([isea4t_id, self.resolution,center_lat, center_lon, avg_edge_len, cell_area])                    
                    sink.addFeature(isea4t_feature, QgsFeatureSink.FastInsert)       
        
                    if feedback.isCanceled():
                        break        
            else:
                total_cells = 20*(4**self.resolution)
                feedback.pushInfo(f"Total cells to be generated: {total_cells}.")
                
                children = get_isea4t_children_cells(isea4t_dggs, isea4t_base_cells, self.resolution)
                for idx, child in enumerate(children):
                    progress = int((idx / total_cells) * 100)
                    feedback.setProgress(progress) 
                     
                    isea4t_cell = DggsCell(child)
                    isea4t_id = isea4t_cell.get_cell_id()
                    cell_polygon = isea4t_cell_to_polygon(isea4t_dggs, isea4t_cell)
                    
                    if self.resolution == 0:
                        cell_polygon = fix_polygon(cell_polygon)
                    elif isea4t_id.startswith('00') or isea4t_id.startswith('09')\
                        or isea4t_id.startswith('14') or isea4t_id.startswith('04') or isea4t_id.startswith('19'):
                        cell_polygon = fix_isea4t_antimeridian_cells(cell_polygon)
                    
                    cell_geometry = QgsGeometry.fromWkt(cell_polygon.wkt)            
                    isea4t_feature = QgsFeature()
                    isea4t_feature.setGeometry(cell_geometry)                     
                        
                    
                    num_edges = 3
                    center_lat, center_lon, avg_edge_len, cell_area = geodesic_dggs_metrics(cell_polygon, num_edges)
                    isea4t_feature.setAttributes([isea4t_id, self.resolution,center_lat, center_lon, avg_edge_len, cell_area])                    
                    sink.addFeature(isea4t_feature, QgsFeatureSink.FastInsert)       
        
                    if feedback.isCanceled():
                        break        
                      
            feedback.pushInfo("ISEA4T DGGS generation completed.")        
            if context.willLoadLayerOnCompletion(dest_id):
                lineColor = QColor.fromRgb(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
                fontColor = QColor('#000000')
                context.layerToLoadOnCompletionDetails(dest_id).setPostProcessor(StylePostProcessor.create(lineColor, fontColor))
            
            return {self.OUTPUT: dest_id}
        else: 
            return {}

class StylePostProcessor(QgsProcessingLayerPostProcessorInterface):
    instance = None
    line_color = None
    font_color = None

    def __init__(self, line_color, font_color):
        self.line_color = line_color
        self.font_color = font_color
        super().__init__()

    def postProcessLayer(self, layer, context, feedback):

        if not isinstance(layer, QgsVectorLayer):
            return
        sym = layer.renderer().symbol().symbolLayer(0)
        sym.setBrushStyle(Qt.NoBrush)
        sym.setStrokeColor(self.line_color)
        label = QgsPalLayerSettings()
        label.fieldName = 'isea4t'
        format = label.format()
        format.setColor(self.font_color)
        format.setSize(8)
        label.setFormat(format)
        labeling = QgsVectorLayerSimpleLabeling(label)
        layer.setLabeling(labeling)
        layer.setLabelsEnabled(True)
        iface.layerTreeView().refreshLayerSymbology(layer.id())

        root = QgsProject.instance().layerTreeRoot()
        layer_node = root.findLayer(layer.id())
        if layer_node:
            layer_node.setCustomProperty("showFeatureCount", True)
            
        iface.mapCanvas().setExtent(layer.extent())
        iface.mapCanvas().refresh()
        
    # Hack to work around sip bug!
    @staticmethod
    def create(line_color, font_color) -> 'StylePostProcessor':
        """
        Returns a new instance of the post processor, keeping a reference to the sip
        wrapper so that sip doesn't get confused with the Python subclass and call
        the base wrapper implementation instead... ahhh sip, you wonderful piece of sip
        """
        StylePostProcessor.instance = StylePostProcessor(line_color, font_color)
        return StylePostProcessor.instance