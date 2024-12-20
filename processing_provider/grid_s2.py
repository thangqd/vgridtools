# -*- coding: utf-8 -*-
"""
grid_vgrid.py
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
    QgsFeatureSink,
    QgsProcessingLayerPostProcessorInterface,
    QgsProcessingParameterExtent,
    QgsProcessingParameterNumber,
    QgsProcessingException,
    QgsProcessingParameterFeatureSink,
    QgsProcessingAlgorithm,
    QgsFields,
    QgsField,
    QgsPointXY, 
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
import os
from ..vgridlibrary.geocode import s2 
from ..vgridlibrary.imgs import Imgs


class GridS2(QgsProcessingAlgorithm):
    EXTENT = 'EXTENT'
    PRECISION = 'PRECISION'
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
        return GridS2()

    def name(self):
        return 'grid_s2'

    def icon(self):
        return QIcon(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'images/grid_gzd.png'))
    
    def displayName(self):
        return self.tr('S2', 'S2')

    def group(self):
        return self.tr('Grid Generator', 'Grid Generator')

    def groupId(self):
        return 'grid'

    def tags(self):
        return self.tr('grid, S2, generator').split(',')
    
    txt_en = 'S2 Grid'
    txt_vi = 'S2 Grid'
    figure = 'images/tutorial/codes2cells.png'

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
                    self.PRECISION,
                    self.tr('Precision'),
                    QgsProcessingParameterNumber.Integer,
                    defaultValue=1,
                    minValue= 0,
                    maxValue= 30,
                    optional=False)
        self.addParameter(param)


        param = QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                'S2')
        self.addParameter(param)
                    
    def prepareAlgorithm(self, parameters, context, feedback):
        self.precision = self.parameterAsInt(parameters, self.PRECISION, context)  
        if self.precision < 0 or self.precision > 30:
            feedback.reportError('Precision parameter must be in range [0,30]')
            return False
         
         # Get the extent parameter
        self.grid_extent = self.parameterAsExtent(parameters, self.EXTENT, context)
        if self.precision > 8 and (self.grid_extent is None or self.grid_extent.isEmpty()):
            feedback.reportError('For performance reason, when precision is greater than 8, the grid extent must be set.')
            return False
        
        return True
    
    def processAlgorithm(self, parameters, context, feedback):
        fields = QgsFields()
        fields.append(QgsField("s2_token", QVariant.String))
        fields.append(QgsField("s2_id", QVariant.String))
        
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
            extent_bbox = [
                [self.grid_extent.xMinimum(), self.grid_extent.yMinimum()],
                [self.grid_extent.xMaximum(), self.grid_extent.yMaximum()]
            ]
        
        region = None
        if extent_bbox:
            region = s2.LatLngRect.from_point_pair(
                s2.LatLng.from_degrees(extent_bbox[0][1], extent_bbox[0][0]),
                s2.LatLng.from_degrees(extent_bbox[1][1], extent_bbox[1][0])
            )

        covering = s2.RegionCoverer()
        covering.min_level = self.precision
        covering.max_level = self.precision
        covering.max_cells = 5000

        # Get covering for the specified region or all regions
        cells = covering.get_covering(region) if region else covering.get_covering(s2.LatLngRect.full())
        total_cells = len(cells)
        
        feedback.pushInfo(f"Total cells to be generated: {total_cells}.")
        if total_cells > 1000000:
            feedback.reportError("For performance reason, it must be lesser than 1000,000. Please input an appropriate extent or precision")
            return {self.OUTPUT: dest_id}
        
        for idx, s2_cell_id in enumerate(cells):
            progress = int((idx / total_cells) * 100)
            feedback.setProgress(progress)

            cell = s2.Cell(s2_cell_id)
            s2_token = s2.CellId.to_token(s2_cell_id)
            vertices = []
            for i in range(4):  # S2 cells are quads
                vertex = cell.get_vertex(i)
                latlng = s2.LatLng.from_point(vertex)
                vertices.append([latlng.lng().degrees, latlng.lat().degrees])
            vertices.append(vertices[0])  # Close the ring

            cell_geometry = QgsGeometry.fromPolygonXY([[QgsPointXY(x, y) for x, y in vertices]])

            # Filter cells by extent if it exists
            if extent_bbox:
                if not cell_geometry.intersects(QgsGeometry.fromRect(self.grid_extent)):
                    continue

            feature = QgsFeature()
            feature.setGeometry(cell_geometry)
            feature.setAttributes([s2_token,str(s2_cell_id.id())])
            sink.addFeature(feature, QgsFeatureSink.FastInsert)

            if idx % 10000 == 0:  # Log progress every 10000 cells
                feedback.pushInfo(f"Processed {idx} of {total_cells} cells...")

            if feedback.isCanceled():
                break
        
        feedback.pushInfo("S2 grid generation completed.")
        if context.willLoadLayerOnCompletion(dest_id):
            lineColor = QColor('#FF0000')
            fontColor = QColor('#000000')
            context.layerToLoadOnCompletionDetails(dest_id).setPostProcessor(StylePostProcessor.create(lineColor, fontColor))
        
        return {self.OUTPUT: dest_id}


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
        label.fieldName = 's2_token'
        format = label.format()
        format.setColor(self.font_color)
        format.setSize(8)
        label.setFormat(format)
        labeling = QgsVectorLayerSimpleLabeling(label)
        layer.setLabeling(labeling)
        layer.setLabelsEnabled(True)
        iface.layerTreeView().refreshLayerSymbology(layer.id())

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