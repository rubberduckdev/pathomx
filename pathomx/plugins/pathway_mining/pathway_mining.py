# -*- coding: utf-8 -*-
from __future__ import unicode_literals

# Import PyQt5 classes
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtWebKit import *
from PyQt5.QtNetwork import *
from PyQt5.QtWidgets import *
from PyQt5.QtWebKitWidgets import *
from PyQt5.QtPrintSupport import *

from plugins import AnalysisPlugin

from collections import defaultdict

import os

import ui, utils
from data import DataSet, DataDefinition

import numpy as np

from db import Compound, Gene, Protein


METAPATH_MINING_TYPE_CODE = ('c', 'u', 'd', 'm', 't')
METAPATH_MINING_TYPE_TEXT = (
    'Compound change scores for pathway',
    'Compound up-regulation scores for pathway', 
    'Compound down-regulation scores for pathway',
    'Number compounds with data per pathway',
    'Pathway overall tendency',
)


# Dialog box for Metabohunter search options
class PathwayMiningConfigPanel(ui.ConfigPanel):
    
    def __init__(self, *args, **kwargs):
        super(PathwayMiningConfigPanel, self).__init__(*args, **kwargs)        
        
        self.cb_miningType = QComboBox()
        self.cb_miningType.addItems( METAPATH_MINING_TYPE_TEXT )
        self.cb_miningType.setCurrentIndex( METAPATH_MINING_TYPE_CODE.index( self.config.get('/Data/MiningType') ) )

        self.xb_miningRelative = QCheckBox('Relative score to pathway size') 
        self.xb_miningRelative.setChecked( bool(self.config.get('/Data/MiningRelative') ) )

        self.xb_miningShared = QCheckBox('Share compound scores between pathways') 
        self.xb_miningShared.setChecked( bool(self.config.get('/Data/MiningShared') ) )
                        

        self.sb_miningDepth = QSpinBox()
        self.sb_miningDepth.setMinimum(1)
        self.sb_miningDepth.setValue( int( self.config.get('/Data/MiningDepth') ) )
        
        self.layout.addWidget(self.cb_miningType)
        self.layout.addWidget(self.xb_miningRelative)
        self.layout.addWidget(self.xb_miningShared)
        self.layout.addWidget(self.sb_miningDepth)
        
        self.finalise()
         


class PathwayMiningApp( ui.AnalysisApp ):
    def __init__(self, **kwargs):
        super(PathwayMiningApp, self).__init__(**kwargs)

        # Define automatic mapping (settings will determine the route; allow manual tweaks later)
        self.addDataToolBar()
        self.addExperimentToolBar()
        
        self.config.set_defaults({
            '/Data/MiningActive':False,
            '/Data/MiningDepth': 5,
            '/Data/MiningType': 'c',
            '/Data/MiningRelative': False,
            '/Data/MiningShared': True,
        })

        #t = self.getCreatedToolbar('Pathway mining', 'pathway_mining')
        #miningSetup = QAction( QIcon( os.path.join( self.plugin.path, 'icon-16.png' ) ), 'Set up pathway mining \u2026', self.m)
        #miningSetup.setStatusTip('Set parameters for pathway mining')
        #miningSetup.triggered.connect(self.onMiningSettings)
        #t.addAction(miningSetup)

        self.data.add_input('input') # Add input slot        
        self.data.add_output('output')
        self.table = QTableView()        
        self.table.setModel( self.data.o['output'].as_table )
        
        self.views.addTab(self.table, 'Table')
        # Setup data consumer options
        self.data.consumer_defs.append( 
            DataDefinition('input', {
            'entities_t':   (None,['Compound','Gene','Protein']), 
            }, title='Source compound, gene or protein data')
        )
        
        self.addConfigPanel( PathwayMiningConfigPanel, 'Pathway Mining')

        self.finalise()

    def generate(self, input=None):
        dsi = input
        # Iterate all the compounds in the current analysis
        # Assign score to each of the compound's pathways
        # Sum up, crop and return a list of pathway_ids to display
        # Pass this in as the list to view
        # + requested pathways, - excluded pathways
        if dsi == False:
            raise BaseException
            
        db = self.m.db

        mining_depth = self.config.get('/Data/MiningDepth')
        mining_type= self.config.get('/Data/MiningType')

        pathway_scores = defaultdict( int )
        print "Mining using '%s'" % mining_type
        
        for n, entity in enumerate(dsi.entities[1]):
            if entity == None:
                continue # Skip

            score = dsi.data[0,n]
            #score = self.analysis[ m_id ]['score']
            
            # 1' neighbours; 2' neighbours etc. add score
            # Get a list of methods in connected reactions, add their score % to this compound
            # if m_id in db.compounds.keys():
            #    n_compounds = [r.compounds for r in db.compounds[ m_id ].reactions ]
            #     print n_compounds
            #     n_compounds = [m for ml in n_compounds for m in ml if n_m.id in self.analysis and m.id != m_id ]
            #     for n_m in n_compounds:
            #         score += self.analysis[ n_m.id ]['score'] * 0.5

            # Get the entity's pathways
            pathways = entity.pathways
            if pathways == []:
                continue   
                
            if self.config.get('/Data/MiningShared'):
                # Share the change score between the associated pathways
                # this prevents compounds having undue influence
                score = score / len(pathways)    
        
            for p in pathways:
                mining_val = {
                    'c': abs( score),
                    'u': max( 0, score),
                    'd': abs( min( 0, score ) ),
                    'm': 1.0,
                    't': score,
                    }
                pathway_scores[ p ] += mining_val[ mining_type ]
                    
    
        # If we're using tendency scaling; abs the scores here
        if mining_type == 't':
            for p,v  in pathway_scores.items():
                pathway_scores[p] = abs( v )
            
    
        # If we're pruning, then remove any pathways not in keep_pathways
        if self.config.get('/Data/MiningRelative'):
            print "Scaling pathway scores to pathway sizes..."
            for p,v in pathway_scores.items():
                pathway_scores[p] = float(v) / len( p.reactions )
    
        pathway_scorest = pathway_scores.items() # Switch it to a dict so we can sort
        pathway_scorest = [(p,v) for p,v in pathway_scorest if v>0] # Remove any scores of 0
        pathway_scorest.sort(key=lambda tup: tup[1], reverse=True) # Sort by scores (either system)
        
        # Get top N defined by mining_depth parameter
        keep_pathways = pathway_scorest[0:mining_depth]
        remaining_pathways = pathway_scorest[mining_depth+1:mining_depth+100]

        print "Mining recommended %d out of %d" % ( len( keep_pathways ), len(pathway_scores) )
       
        for n,p in enumerate(keep_pathways):
            print "- %d. %s [%.2f]" % (n+1, p[0].name, p[1])

        #self.analysis['mining_ranked_remaining_pathways'] = []
                        
        #if remaining_pathways:
        #    print "Note: Next pathways by current scoring method are..."
        #    for n2,p in enumerate(remaining_pathways):
        #        print "- %d. %s [%.2f]" % (n+n2+1, db.pathways[ p[0] ].name, p[1])
        #        self.analysis['mining_ranked_remaining_pathways'].append( p[0] )

        #self.analysis_suggested_pathways = [db.pathways[p[0]] for p in pathway_scorest]
        dso = DataSet( size=(1, len(keep_pathways) )  )
        dso.entities[1] = [k for k,v in keep_pathways]
        dso.labels[1] = [k.name for k,v in keep_pathways]
        dso.data = np.array( [v for k,v in keep_pathways], ndmin=2 )
    
        dso.labels[0][0] = "Pathway mining scores"


        return {'output':dso}
        

    def onMiningSettings(self):
        """ Open the mining setup dialog to define conditions, ranges, class-comparisons, etc. """
        dialog = dialogMiningSettings(parent=self)
        ok = dialog.exec_()
        if ok:
            self.config.set('/Data/MiningDepth', dialog.sb_miningDepth.value() )
            self.config.set('/Data/MiningType', METAPATH_MINING_TYPE_CODE[ dialog.cb_miningType.currentIndex() ] )
            self.config.set('/Data/MiningRelative', dialog.xb_miningRelative.isChecked() )
            self.config.set('/Data/MiningShared', dialog.xb_miningShared.isChecked() )

            # Update the toolbar dropdown to match
            self.sb_miningDepth.setValue( dialog.sb_miningDepth.value() )        

    def onModifyMiningDepth(self):
        """ Change mine depth via toolbar spinner """    
        self.config.set('/Data/MiningDepth', self.sb_miningDepth.value())

            
    def onDefineExperiment(self):
        """ Open the experimental setup dialog to define conditions, ranges, class-comparisons, etc. """
        dialog = dialogDefineExperiment(parent=self)
        ok = dialog.exec_()
        if ok:
            # Regenerate the graph view
            self.config.set('experiment_control', dialog.cb_control.currentText() )
            self.config.set('experiment_test', dialog.cb_test.currentText() )
        
            # Update toolbar to match any change caused by timecourse settings
            self.update_view_callback_enabled = False # Disable to stop multiple refresh as updating the list
            self.cb_control.clear()
            self.cb_test.clear()

            self.cb_control.addItems( [dialog.cb_control.itemText(i) for i in range(dialog.cb_control.count())] )
            self.cb_test.addItems( [dialog.cb_test.itemText(i) for i in range(dialog.cb_test.count())] )
    

        
        
class PathwayMining(AnalysisPlugin):

    def __init__(self, **kwargs):
        super(PathwayMining, self).__init__(**kwargs)
        PathwayMiningApp.plugin = self
        self.register_app_launcher( PathwayMiningApp )
