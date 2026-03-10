"""
2D RC Building Analysis App
============================

A comprehensive Streamlit application for creating 2D reinforced concrete frame building models
for structural analysis in OpenSeesPy. This app follows the logic of master_script_pushover.py
and uses opseestools for 2D planar frame modeling.

FEATURES
--------
- **Building Geometry**: Define 2D planar frame with X coordinates (spans) and Y coordinates (heights)
- **Material Definition**: Create concrete and steel material sets with different detailing levels
- **Section Properties**: Define rectangular RC sections with reinforcement configurations
- **Element Assignment**: Assign sections to columns and beams across all floors
- **Model Visualization**: Interactive 2D frame elevation plots with element information
- **Load Application**: Define gravity loads on beams for analysis
- **Model Persistence**: Save/load complete models for analysis workflows
- **Gravity Analysis**: Run gravity load analysis
- **Pushover Analysis**: Perform nonlinear static pushover with results visualization

WORKFLOW TABS
-------------
1. **Load/New Model**: Start new or load existing 2D model
2. **Building Geometry**: Define X coordinates (spans) and Y coordinates (story heights)
3. **Materials**: Create concrete/steel material combinations
4. **Sections**: Define cross-sectional properties and reinforcement
5. **Element Assignment**: Assign sections to columns and beams
6. **Model Visualization**: Review 2D frame and create structural elements
7. **Loads**: Apply gravity loads to beams
8. **Create and Save Model**: Export model for future use
9. **Analysis**: Gravity and pushover analysis with results visualization

TECHNICAL DETAILS
-----------------
- **Backend**: OpenSeesPy with opseestools.utilidades and opseestools.analisis
- **Model Type**: 2D planar frame (ndm=2, ndf=3)
- **Materials**: Confined/unconfined concrete + steel reinforcement
- **Elements**: Nonlinear beam-column elements with fiber sections
- **Boundary Conditions**: Fixed supports at base level (fixY)
- **File Format**: Pickle (.pkl) for complete model serialization
- **Visualization**: Plotly-based 2D frame elevation plots

KEY DIFFERENCES FROM 3D APP
----------------------------
- 2D model instead of 3D (no Z-axis, only X-Y plane)
- Single plane of beams (no Y-direction beams)
- Simplified element assignment (no beamY)
- Uses ut.creategrid() instead of ut.creategrid3d()
- Uses ut.create_elements2() for 2D element creation
- Masses are NOT included in nodes (added later as separate feature)

DEPENDENCIES
------------
- streamlit
- openseespy
- opseestools (analisis, utilidades)
- numpy, pandas
- plotly
- pickle, os

AUTHOR
------
Created for 2D RC frame pushover analysis following master_script_pushover.py logic.
"""

import streamlit as st
from openseespy.opensees import *
import opseestools.analisis as an
import opseestools.utilidades as ut
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pickle
import os

# Import functions from library module
import library_2d as lib

# =============================================================================
# CODE ORGANIZATION:
# 1. Session state management
# 2. UI helper functions
# 3. Tab rendering functions (main UI)
# 4. Main application entry point
# =============================================================================

# Use constants from library
REBAR_AREAS = lib.REBAR_AREAS
DETAILING_OPTIONS = lib.DETAILING_OPTIONS


# ==================== SESSION STATE INITIALIZATION ====================
def initialize_session_state():
    """
    Initialize all Streamlit session state variables for the 2D application.

    Key state variables for 2D model:
    - model_created: Whether building geometry has been defined
    - materials: Dictionary of defined material sets
    - sections: Dictionary of defined cross-sections
    - column_assignments: Section assignments per floor [floor][x_position]
    - beam_assignments: Section assignments per floor [floor][span]
    - elements_created: Flag for model element creation
    - loads_applied: Whether gravity loads have been defined
    - Various analysis flags for workflow tracking
    """
    defaults = {
        'model_created': False,
        'materials': {},
        'sections': {},
        'column_assignments': {},
        'beam_assignments': {},
        'elements_created': False,
        'loads_applied': False,
        'masses_assigned': False,
        'nodal_loads_assigned': False,
        'node_masses': {},
        'node_loads': {},
        'gravity_analysis_done': False,
        'modal_analysis_done': False,
        'pushover_analysis_done': False,
        'project_name': "building_2d",
        'coordx': None,
        'coordy': None,
        'editing_mode': False,
        'loaded_model_name': None,
        'model_modified': False,
        'tagcols': None,
        'tagbeams': None,
        'column_info': None,
        'beam_info': None,
        # Infill-related state
        'masonry_materials': {},
        'infill_assignments': {},
        'width_percentage': 0.25,
        'diagonal_pairs': None,
        'diagonal_lengths': None,
        'infills_assigned': False,
        'model_node_tags': None,
    }
    
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# ==================== UI HELPER FUNCTIONS ====================
# These functions remain here as they interact with Streamlit session state

def create_section_ui(section_tag, H, B, cover, material_props, bars_config):
    """Create OpenSeesPy section"""
    # Handle middle bars = 0 case
    # If no middle bars, only pass 4 rebar parameters (like master_script for beams)
    bars_middle = bars_config['bars_middle']
    
    if bars_middle == 0:
        # Call with only 4 rebar parameters (no middle bars)
        ut.create_rect_RC_section(
            section_tag,
            H, B, cover,
            material_props['conf_tag'],
            material_props['noconf_tag'],
            material_props['acero_tag'],
            bars_config['bars_top'],
            bars_config['area_top'],
            bars_config['bars_bottom'],
            bars_config['area_bottom']
        )
    else:
        # Call with all 6 rebar parameters (including middle bars)
        ut.create_rect_RC_section(
            section_tag,
            H, B, cover,
            material_props['conf_tag'],
            material_props['noconf_tag'],
            material_props['acero_tag'],
            bars_config['bars_top'],
            bars_config['area_top'],
            bars_config['bars_bottom'],
            bars_config['area_bottom'],
            bars_middle,
            bars_config['area_middle']
        )


def create_section_visualization(H, B, cover, bars_top, bars_bottom, bars_middle):
    """
    Create a visualization of the rectangular RC section showing:
    - Section outline
    - Concrete cover zones
    - Steel reinforcement bar positions
    
    Parameters:
    -----------
    H : float
        Section height (m)
    B : float
        Section width/base (m)
    cover : float
        Concrete cover (m)
    bars_top : int
        Number of bars at top
    bars_bottom : int
        Number of bars at bottom
    bars_middle : int
        Total number of bars on sides (split equally: half on each side)
    
    Returns:
    --------
    plotly.graph_objects.Figure
    """
    fig = go.Figure()
    
    # Section dimensions in mm for better visualization
    H_mm = H * 1000
    B_mm = B * 1000
    cover_mm = cover * 1000
    
    # Outer rectangle (gross section)
    fig.add_trace(go.Scatter(
        x=[0, B_mm, B_mm, 0, 0],
        y=[0, 0, H_mm, H_mm, 0],
        fill='toself',
        fillcolor='lightgray',
        line=dict(color='black', width=2),
        mode='lines',
        name='Concrete Section',
        hoverinfo='skip'
    ))
    
    # Inner rectangle (core concrete)
    fig.add_trace(go.Scatter(
        x=[cover_mm, B_mm - cover_mm, B_mm - cover_mm, cover_mm, cover_mm],
        y=[cover_mm, cover_mm, H_mm - cover_mm, H_mm - cover_mm, cover_mm],
        fill='toself',
        fillcolor='wheat',
        line=dict(color='gray', width=1, dash='dash'),
        mode='lines',
        name='Core Concrete',
        hoverinfo='skip'
    ))
    
    # Rebar diameter for visualization (assume 20mm for display)
    rebar_radius = 10  # mm
    
    # Top bars
    if bars_top > 0:
        top_y = H_mm - cover_mm
        if bars_top == 1:
            top_x_positions = [B_mm / 2]
        else:
            top_x_positions = np.linspace(cover_mm, B_mm - cover_mm, bars_top)
        
        for x_pos in top_x_positions:
            fig.add_trace(go.Scatter(
                x=[x_pos],
                y=[top_y],
                mode='markers',
                marker=dict(size=12, color='red', symbol='circle', 
                           line=dict(color='darkred', width=1)),
                name='Top Rebar' if x_pos == top_x_positions[0] else '',
                showlegend=bool(x_pos == top_x_positions[0]),
                hovertemplate=f'Top Bar<br>x: {x_pos:.0f} mm<br>y: {top_y:.0f} mm<extra></extra>'
            ))
    
    # Bottom bars
    if bars_bottom > 0:
        bottom_y = cover_mm
        if bars_bottom == 1:
            bottom_x_positions = [B_mm / 2]
        else:
            bottom_x_positions = np.linspace(cover_mm, B_mm - cover_mm, bars_bottom)
        
        for x_pos in bottom_x_positions:
            fig.add_trace(go.Scatter(
                x=[x_pos],
                y=[bottom_y],
                mode='markers',
                marker=dict(size=12, color='blue', symbol='circle',
                           line=dict(color='darkblue', width=1)),
                name='Bottom Rebar' if x_pos == bottom_x_positions[0] else '',
                showlegend=bool(x_pos == bottom_x_positions[0]),
                hovertemplate=f'Bottom Bar<br>x: {x_pos:.0f} mm<br>y: {bottom_y:.0f} mm<extra></extra>'
            ))
    
    # Middle bars (split equally on each side)
    if bars_middle > 0:
        bars_per_side = bars_middle // 2
        
        if bars_per_side > 0:
            # Exclude corners (already have top/bottom bars)
            if bars_per_side == 1:
                middle_y_positions = [H_mm / 2]
            else:
                # Distribute along height, excluding top and bottom cover zones
                middle_y_positions = np.linspace(cover_mm + (H_mm - 2*cover_mm)/(bars_per_side + 1), 
                                                H_mm - cover_mm - (H_mm - 2*cover_mm)/(bars_per_side + 1), 
                                                bars_per_side)
            
            # Left side
            for idx, y_pos in enumerate(middle_y_positions):
                fig.add_trace(go.Scatter(
                    x=[cover_mm],
                    y=[y_pos],
                    mode='markers',
                    marker=dict(size=12, color='green', symbol='circle',
                               line=dict(color='darkgreen', width=1)),
                    name='Side Rebar (Left)' if idx == 0 else '',
                    showlegend=(idx == 0),
                    hovertemplate=f'Left Side Bar<br>x: {cover_mm:.0f} mm<br>y: {y_pos:.0f} mm<extra></extra>'
                ))
            
            # Right side
            for idx, y_pos in enumerate(middle_y_positions):
                fig.add_trace(go.Scatter(
                    x=[B_mm - cover_mm],
                    y=[y_pos],
                    mode='markers',
                    marker=dict(size=12, color='green', symbol='circle',
                               line=dict(color='darkgreen', width=1)),
                    name='Side Rebar (Right)' if idx == 0 else '',
                    showlegend=(idx == 0),
                    hovertemplate=f'Right Side Bar<br>x: {B_mm - cover_mm:.0f} mm<br>y: {y_pos:.0f} mm<extra></extra>'
                ))
    
    # Add dimension annotations
    fig.add_annotation(
        x=B_mm/2, y=-50,
        text=f"B = {B*1000:.0f} mm",
        showarrow=False,
        font=dict(size=12, color='black', family='Arial Black')
    )
    
    fig.add_annotation(
        x=-50, y=H_mm/2,
        text=f"H = {H*1000:.0f} mm",
        textangle=-90,
        showarrow=False,
        font=dict(size=12, color='black', family='Arial Black')
    )
    
    fig.add_annotation(
        x=B_mm + 50, y=cover_mm,
        text=f"c = {cover*1000:.0f} mm",
        showarrow=True,
        arrowhead=2,
        arrowsize=1,
        arrowwidth=1,
        ax=20,
        ay=0,
        font=dict(size=10, color='gray')
    )
    
    # Update layout
    fig.update_layout(
        title=dict(
            text=f"Section Preview: {H*1000:.0f}mm × {B*1000:.0f}mm<br>"
                 f"<sub>Top: {bars_top} bars | Bottom: {bars_bottom} bars | Sides: {bars_middle} bars ({bars_middle//2} per side)</sub>",
            font=dict(size=14)
        ),
        xaxis=dict(
            title='Width (mm)',
            scaleanchor='y',
            scaleratio=1,
            range=[-100, B_mm + 100]
        ),
        yaxis=dict(
            title='Height (mm)',
            range=[-100, H_mm + 100]
        ),
        showlegend=True,
        legend=dict(x=1.05, y=1),
        height=500,
        hovermode='closest',
        plot_bgcolor='white',
        paper_bgcolor='white'
    )
    
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='lightgray')
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='lightgray')
    
    return fig


# ==================== TAB 0: LOAD/NEW MODEL ====================
def render_load_model_tab():
    """
    Render Load/New Model tab - allows users to either start a new model or load an existing one.
    """
    st.header("Load or Create New Model")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🆕 Start New Model")
        st.markdown("""
        Create a brand new 2D building model from scratch.
        
        **Next steps after creating new model:**
        1. **Tab 1 - Building Geometry**: Define X and Y coordinates
        2. **Tab 2 - Materials**: Create material sets
        3. **Tab 3 - Sections**: Define cross-sections
        4. **Tab 4 - Element Assignment**: Assign sections to columns/beams
        5. **Tab 5 - Model Visualization**: Create structural elements
        6. **Tab 6 - Loads**: Apply gravity loads
        7. **Tab 7 - Save Model**: Export model
        8. **Tab 8 - Analysis**: Run gravity and pushover
        """)
        
        if st.button("🚀 Start New Model", type="primary", key="start_new"):
            # Reset all session state
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            initialize_session_state()
            st.success("✅ New model initialized!")
            st.info("💡 Go to the 'Building Geometry' tab to begin.")
            st.rerun()
    
    with col2:
        st.subheader("📂 Load Existing Model")
        st.markdown("""
        Load a previously saved 2D building model (.pkl file).
        
        **After loading, you must:**
        1. **Tab 1 - Building Geometry**: Click "Create Model" to recreate OpenSeesPy nodes
        2. **Tab 2 - Materials**: Confirm all loaded materials (or use "Confirm All" button)
        3. **Tab 3 - Sections**: Confirm all loaded sections (or use "Confirm All" button)
        4. **Tab 4 - Element Assignment**: Review assignments (already loaded from file)
        5. **Tab 5 - Model Visualization**: Click "Create Elements" to build structural elements
        6. **Tab 6-8**: Continue with loads and analysis as needed
        """)
        
        uploaded_file = st.file_uploader(
            "Choose a .pkl file",
            type=['pkl'],
            help="Select a 2D building model file to load"
        )
        
        if uploaded_file is not None:
            if st.button("📥 Load Model", type="primary", key="load_model"):
                try:
                    # Load the pickle file
                    model_data = pickle.load(uploaded_file)
                    
                    # Validate it's a 2D model
                    if 'coordz' in model_data:
                        st.error("❌ This appears to be a 3D model file. Please load a 2D model.")
                        return
                    
                    # Load data into session state
                    st.session_state.project_name = model_data.get('project_name', 'loaded_model_2d')
                    st.session_state.coordx = model_data['coordx']
                    st.session_state.coordy = model_data['coordy']
                    st.session_state.materials = model_data.get('materials', {})
                    st.session_state.sections = model_data.get('sections', {})
                    st.session_state.column_assignments = model_data.get('column_assignments', {})
                    st.session_state.beam_assignments = model_data.get('beam_assignments', {})
                    
                    # Load status flags
                    st.session_state.model_created = model_data.get('model_created', False)
                    st.session_state.elements_created = model_data.get('elements_created', False)
                    st.session_state.loads_applied = model_data.get('loads_applied', False)
                    
                    # Load load data if it exists
                    if st.session_state.loads_applied:
                        st.session_state.load_type = model_data.get('load_type', 'same')
                        if st.session_state.load_type == 'same':
                            st.session_state.floor_beam_loads = model_data.get('floor_beam_loads', 70.0)
                            st.session_state.roof_beam_loads = model_data.get('roof_beam_loads', 50.0)
                        else:
                            # Load beamwise loads (support both old and new keys)
                            st.session_state.beam_loads_beamwise = model_data.get('beam_loads_beamwise', 
                                                                                  model_data.get('beam_loads_by_floor', {}))
                    
                    # Load masses and nodal loads if they exist
                    st.session_state.masses_assigned = model_data.get('masses_assigned', False)
                    st.session_state.nodal_loads_assigned = model_data.get('nodal_loads_assigned', False)
                    st.session_state.node_masses = model_data.get('node_masses', {})
                    st.session_state.node_loads = model_data.get('node_loads', {})

                    # Load infill data (backward compatible - defaults if not present)
                    st.session_state.masonry_materials = model_data.get('masonry_materials', {})
                    st.session_state.infill_assignments = model_data.get('infill_assignments', {})
                    st.session_state.width_percentage = model_data.get('width_percentage', 0.25)
                    st.session_state.infills_assigned = model_data.get('infills_assigned', False)

                    # Set editing mode
                    st.session_state.editing_mode = True
                    st.session_state.loaded_model_name = uploaded_file.name
                    
                    # Mark loaded materials and sections for confirmation
                    st.session_state.loaded_materials = set(st.session_state.materials.keys())
                    st.session_state.loaded_sections = set(st.session_state.sections.keys())
                    st.session_state.confirmed_materials = set()
                    st.session_state.confirmed_sections = set()
                    
                    st.success(f"✅ Model '{uploaded_file.name}' loaded successfully!")
                    st.info("📋 **Next Steps**: Go to Tab 1 (Building Geometry) and click 'Create Model' to recreate the OpenSeesPy model, then confirm materials and sections in Tabs 2-3.")
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"❌ Error loading model: {str(e)}")
    
    # Show current model status
    if st.session_state.model_created:
        st.markdown("---")
        st.success(f"✅ **Current Model**: {st.session_state.project_name}")
        
        col_status1, col_status2, col_status3, col_status4 = st.columns(4)
        with col_status1:
            st.metric("Geometry", "✅" if st.session_state.model_created else "❌")
        with col_status2:
            st.metric("Materials", len(st.session_state.materials))
        with col_status3:
            st.metric("Sections", len(st.session_state.sections))
        with col_status4:
            st.metric("Elements", "✅" if st.session_state.elements_created else "❌")


# ==================== TAB 1: GEOMETRY ====================
def render_geometry_tab():
    """Render Building Geometry tab for 2D model"""
    st.header("Building Geometry")
    st.markdown("Define the coordinates of nodes in the 2D plane (X-Y). Masses will be added later.")
    
    # Project name
    st.subheader("Project Information")
    project_name = st.text_input(
        "Project Name",
        value=st.session_state.project_name,
        help="Name for the project (will be used for saving files)"
    )
    st.session_state.project_name = project_name
    
    st.markdown("---")
    
    # Pre-populate inputs if editing mode
    default_coordx = ", ".join(map(str, st.session_state.coordx)) if st.session_state.coordx else "0, 5.0, 12.0, 18.0"
    default_coordy = ", ".join(map(str, st.session_state.coordy)) if st.session_state.coordy else "0, 3, 6, 9, 12, 15, 18, 21"
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Horizontal Coordinates")
        
        coordx_input = st.text_area(
            "**X Coordinates (m)** - Column positions",
            value=default_coordx,
            help="Define the horizontal positions of columns. Example: 0, 5.0, 12.0, 18.0"
        )
        
        st.info(f"**Spans**: {len(lib.parse_coordinates(coordx_input)) - 1} bays" if coordx_input else "Enter coordinates")
    
    with col2:
        st.subheader("Vertical Coordinates")
        
        coordy_input = st.text_area(
            "**Y Coordinates (m)** - Story heights",
            value=default_coordy,
            help="Define the vertical positions (story heights). Example: 0, 3, 6, 9, 12, 15, 18, 21"
        )
        
        st.info(f"**Floors**: {len(lib.parse_coordinates(coordy_input)) - 1} stories" if coordy_input else "Enter coordinates")
    
    st.markdown("---")
    
    # Create model button
    if st.button("Create Model", type="primary", key="create_model"):
        try:
            # Parse inputs
            coordx = lib.parse_coordinates(coordx_input)
            coordy = lib.parse_coordinates(coordy_input)
            
            # Validate
            if len(coordx) < 2:
                st.error("⚠️ Need at least 2 X coordinates")
            elif len(coordy) < 2:
                st.error("⚠️ Need at least 2 Y coordinates")
            elif coordy[0] != 0:
                st.error("⚠️ First Y coordinate must be 0 (base level)")
            else:
                # Store in session state
                st.session_state.coordx = coordx
                st.session_state.coordy = coordy
                
                # Create 2D model
                lib.create_opensees_model(coordx, coordy)
                
                st.session_state.model_created = True
                # Reset element and load flags when model is recreated (wipe() was called)
                st.session_state.elements_created = False
                st.session_state.loads_applied = False
                st.session_state.infills_assigned = False

                # Compute diagonal pairs for infill modeling
                diagonal_pairs, diagonal_lengths = lib.get_diagonal_node_pairs(coordx, coordy)
                st.session_state.diagonal_pairs = diagonal_pairs
                st.session_state.diagonal_lengths = diagonal_lengths

                st.success("✅ 2D Model created successfully!")
                if st.session_state.get('editing_mode'):
                    st.info("ℹ️ **Next Steps**: Go to Tabs 2-3 to confirm materials and sections, then Tab 5 to create elements, and Tab 6 to apply loads.")
                
                # Display summary
                st.markdown("### Model Summary")
                col_sum1, col_sum2, col_sum3 = st.columns(3)
                with col_sum1:
                    st.metric("Total Nodes", len(coordx) * len(coordy))
                with col_sum2:
                    st.metric("Number of Floors", len(coordy) - 1)
                with col_sum3:
                    st.metric("Number of Bays", len(coordx) - 1)
                
                # Simple visualization
                st.markdown("### 2D Frame Geometry Preview")
                fig = go.Figure()
                
                # Draw nodes
                for x in coordx:
                    for y in coordy:
                        fig.add_trace(go.Scatter(
                            x=[x], y=[y],
                            mode='markers',
                            marker=dict(size=8, color='blue'),
                            showlegend=False,
                            hovertemplate=f'Node<br>X: {x:.2f}m<br>Y: {y:.2f}m<extra></extra>'
                        ))
                
                # Draw grid lines
                for x in coordx:
                    fig.add_trace(go.Scatter(
                        x=[x, x], y=[min(coordy), max(coordy)],
                        mode='lines',
                        line=dict(color='lightgray', width=1, dash='dash'),
                        showlegend=False,
                        hoverinfo='skip'
                    ))
                
                for y in coordy:
                    fig.add_trace(go.Scatter(
                        x=[min(coordx), max(coordx)], y=[y, y],
                        mode='lines',
                        line=dict(color='lightgray', width=1, dash='dash'),
                        showlegend=False,
                        hoverinfo='skip'
                    ))
                
                fig.update_layout(
                    title="2D Frame Grid",
                    xaxis_title="X Coordinate (m)",
                    yaxis_title="Y Coordinate (m)",
                    height=500,
                    showlegend=False,
                    hovermode='closest'
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
        except Exception as e:
            st.error(f"❌ Error creating model: {str(e)}")
    
    # Display current configuration
    if st.session_state.model_created:
        st.markdown("---")
        st.success("✅ Model geometry is defined!")
        
        # Reminder for edit mode
        if st.session_state.editing_mode:
            st.info("💡 **Edit Mode Reminder**: After loading a model, click 'Create Model' above to recreate the OpenSeesPy model with the loaded geometry before running any analysis.")
        
        with st.expander("View Current Configuration"):
            col_conf1, col_conf2 = st.columns(2)
            with col_conf1:
                st.write("**X Coordinates:**", st.session_state.coordx)
            with col_conf2:
                st.write("**Y Coordinates:**", st.session_state.coordy)


# ==================== TAB 2: MATERIALS ====================
def render_materials_tab():
    """Render Material Definition tab"""
    st.header("Material Definition")
    st.markdown("Define concrete and steel materials for your structural elements.")
    
    if not st.session_state.model_created:
        st.warning("⚠️ Please create the model in the 'Building Geometry' tab first.")
        return
    
    # Show loaded materials management in edit mode
    if st.session_state.editing_mode and st.session_state.materials:
        # Track which materials have been confirmed/created in OpenSeesPy
        if 'confirmed_materials' not in st.session_state:
            st.session_state.confirmed_materials = set()
        if 'loaded_materials' not in st.session_state:
            st.session_state.loaded_materials = set()
        
        # Only show loaded materials that need confirmation
        loaded_materials_list = {name: props for name, props in st.session_state.materials.items() 
                                if name in st.session_state.get('loaded_materials', set())}
        
        if loaded_materials_list:
            st.markdown("---")
            st.subheader("📋 Manage Loaded Materials")
            st.info("⚠️ Loaded materials need to be confirmed to recreate them in OpenSeesPy. You can also edit or delete them.")
        
        for material_name, props in list(loaded_materials_list.items()):
            with st.expander(f"Material: **{material_name}** {'✅ Confirmed' if material_name in st.session_state.confirmed_materials else '⚠️ Not Confirmed'}", expanded=material_name not in st.session_state.confirmed_materials):
                col_info1, col_info2 = st.columns(2)
                
                with col_info1:
                    st.write(f"**Properties:**")
                    st.write(f"- f'c: {props['fc']} MPa")
                    st.write(f"- fy: {props['fy']} MPa")
                    st.write(f"- Detailing: {props['detailing']}")
                    st.write(f"**OpenSees Tags:**")
                    st.write(f"- Unconfined: {props['noconf_tag']}")
                    st.write(f"- Confined: {props['conf_tag']}")
                    st.write(f"- Steel: {props['acero_tag']}")
                
                with col_info2:
                    st.write("**Actions:**")
                    
                    # Confirm button
                    if material_name not in st.session_state.confirmed_materials:
                        if st.button(f"✅ Confirm & Create", key=f"confirm_mat_{material_name}", type="primary"):
                            try:
                                # Recreate the material in OpenSeesPy
                                material_index = (props['noconf_tag'] // 100) - 1
                                lib.create_material(props['fc'], props['fy'], props['detailing'], material_index)
                                st.session_state.confirmed_materials.add(material_name)
                                st.success(f"✅ Material '{material_name}' created in OpenSeesPy!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Error creating material: {str(e)}")
                    else:
                        st.success("✅ Already confirmed")
                    
                    # Delete button
                    if st.button(f"🗑️ Delete", key=f"delete_mat_{material_name}", type="secondary"):
                        # Check if material is used by any section
                        sections_using_material = [s for s, p in st.session_state.sections.items() if p['material'] == material_name]
                        if sections_using_material:
                            st.error(f"⚠️ Cannot delete! Material is used by sections: {', '.join(sections_using_material)}")
                        else:
                            del st.session_state.materials[material_name]
                            if material_name in st.session_state.confirmed_materials:
                                st.session_state.confirmed_materials.remove(material_name)
                            st.warning(f"⚠️ Material '{material_name}' deleted!")
                            st.rerun()
        
        # Confirm all button
        unconfirmed = [name for name in st.session_state.materials.keys() if name not in st.session_state.confirmed_materials]
        if unconfirmed:
            st.markdown("---")
            if st.button(f"✅ Confirm All {len(unconfirmed)} Unconfirmed Materials", type="primary", key="confirm_all_materials"):
                errors = []
                for material_name in unconfirmed:
                    try:
                        props = st.session_state.materials[material_name]
                        material_index = (props['noconf_tag'] // 100) - 1
                        lib.create_material(props['fc'], props['fy'], props['detailing'], material_index)
                        st.session_state.confirmed_materials.add(material_name)
                    except Exception as e:
                        errors.append(f"{material_name}: {str(e)}")
                
                if not errors:
                    st.success(f"✅ All {len(unconfirmed)} materials confirmed and created in OpenSeesPy!")
                else:
                    st.error(f"❌ Errors occurred:\n" + "\n".join(errors))
                st.rerun()
        else:
            st.success("✅ All loaded materials have been confirmed!")
    
    st.markdown("---")
    st.subheader("➕ Add New Material Set")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        material_name = st.text_input(
            "Material Name",
            value="",
            placeholder="e.g., Concrete_28MPa",
            help="Enter a unique name for this material"
        )
    
    with col2:
        fc = st.number_input(
            "f'c - Concrete Strength (MPa)",
            min_value=10.0,
            max_value=100.0,
            value=28.0,
            step=1.0,
            help="Concrete compressive strength"
        )
    
    with col3:
        fy = st.number_input(
            "fy - Steel Yield Strength (MPa)",
            min_value=200.0,
            max_value=600.0,
            value=420.0,
            step=10.0,
            help="Steel reinforcement yield strength"
        )
    
    detailing_level = st.selectbox(
        "Detailing Level",
        options=DETAILING_OPTIONS,
        help="DES: Special detailing, DMO: Moderate detailing, PreCode: Pre-code"
    )
    
    if st.button("Add Material", type="primary", key="add_material"):
        if material_name == "":
            st.error("⚠️ Please enter a material name")
        elif material_name in st.session_state.materials:
            st.error(f"⚠️ Material '{material_name}' already exists. Use a different name.")
        else:
            try:
                material_index = len(st.session_state.materials)
                material_props = lib.create_material(fc, fy, detailing_level, material_index)
                st.session_state.materials[material_name] = material_props
                # Auto-confirm newly added materials (they were just created in OpenSeesPy)
                if 'confirmed_materials' not in st.session_state:
                    st.session_state.confirmed_materials = set()
                st.session_state.confirmed_materials.add(material_name)
                st.success(f"✅ Material '{material_name}' added successfully!")
            except Exception as e:
                st.error(f"❌ Error creating material: {str(e)}")
    
    # Display existing materials
    if st.session_state.materials:
        st.markdown("---")
        st.subheader("Defined Materials Sets")
        
        materials_data = []
        for name, props in st.session_state.materials.items():
            materials_data.append({
                'Material Set Name': name,
                "f'c (MPa)": props['fc'],
                'fy (MPa)': props['fy'],
                'Detailing': props['detailing'],
                'Unconfined Tag': props['noconf_tag'],
                'Confined Tag': props['conf_tag'],
                'Steel Tag': props['acero_tag']
            })
        
        df_materials = pd.DataFrame(materials_data)
        st.dataframe(df_materials, use_container_width=True)
    else:
        st.info("ℹ️ No materials defined yet. Add your first material above.")


# ==================== TAB: MASONRY MATERIALS ====================
def render_masonry_materials_tab():
    """Render Masonry Materials tab for defining infill wall materials."""
    st.header("Masonry Materials")
    st.markdown("Define masonry materials for infill wall modeling. Each material is defined by its compressive strength (f'm) and brick type.")

    if not st.session_state.model_created:
        st.warning("⚠️ Please create the model in the 'Building Geometry' tab first.")
        return

    # --- Add New Masonry Material ---
    st.subheader("Add New Masonry Material")

    col1, col2, col3 = st.columns(3)

    with col1:
        mas_name = st.text_input(
            "Material Name",
            value="Masonry 1",
            help="Give a descriptive name to this masonry material",
            key="mas_mat_name"
        )

    with col2:
        fm_value = st.number_input(
            "f'm (MPa)",
            min_value=0.5,
            max_value=30.0,
            value=4.0,
            step=0.5,
            help="Masonry compressive strength in MPa",
            key="mas_fm_input"
        )

    with col3:
        brick_type = st.selectbox(
            "Brick Type",
            options=['VP', 'HP'],
            help="VP = Vertical Perforation (Em=775*fm), HP = Horizontal Perforation (Em=622*fm)",
            key="mas_brick_type"
        )

    if st.button("Add Masonry Material", type="primary", key="add_masonry_mat"):
        if mas_name in st.session_state.masonry_materials:
            st.error(f"⚠️ A masonry material named '{mas_name}' already exists.")
        elif mas_name in st.session_state.materials:
            st.error(f"⚠️ This name conflicts with an existing RC material.")
        else:
            # Generate negative tag to avoid collision with RC material tags
            existing_tags = [props['tag'] for props in st.session_state.masonry_materials.values()]
            if existing_tags:
                new_tag = min(existing_tags) - 1
            else:
                new_tag = -1

            # Create the material in OpenSeesPy
            try:
                lib.col_infill(fm_value, new_tag, brick_type)
                st.session_state.masonry_materials[mas_name] = {
                    'fm': fm_value,
                    'brick_type': brick_type,
                    'tag': new_tag,
                }
                st.success(f"✅ Masonry material '{mas_name}' created (tag={new_tag}, f'm={fm_value} MPa, type={brick_type})")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Error creating masonry material: {str(e)}")

    # --- Display Existing Masonry Materials ---
    st.markdown("---")
    st.subheader("Defined Masonry Materials")

    if st.session_state.masonry_materials:
        mas_data = []
        for name, props in st.session_state.masonry_materials.items():
            mas_data.append({
                'Name': name,
                "f'm (MPa)": props['fm'],
                'Brick Type': props['brick_type'],
                'Tag': props['tag'],
            })
        df_mas = pd.DataFrame(mas_data)
        st.dataframe(df_mas, use_container_width=True)

        # Delete material
        st.markdown("**Delete a masonry material:**")
        mat_to_delete = st.selectbox(
            "Select material to delete:",
            options=list(st.session_state.masonry_materials.keys()),
            key="mas_mat_delete_select"
        )
        if st.button("🗑️ Delete Material", key="delete_masonry_mat"):
            del st.session_state.masonry_materials[mat_to_delete]
            # Also clear any infill assignments that used this material
            for floor_data in st.session_state.infill_assignments.values():
                for span_data in floor_data.values():
                    if span_data.get('material_name') == mat_to_delete:
                        span_data['material_name'] = 'None'
            st.success(f"✅ Masonry material '{mat_to_delete}' deleted.")
            st.rerun()
    else:
        st.info("ℹ️ No masonry materials defined yet. Add your first material above.")


# ==================== TAB 3: SECTIONS ====================
def render_sections_tab():
    """Render Sections tab"""
    st.header("Sections")
    st.markdown("Define cross-sections for structural elements (columns and beams).")
    
    if not st.session_state.model_created:
        st.warning("⚠️ Please create the model in the 'Building Geometry' tab first.")
        return
    elif not st.session_state.materials:
        st.warning("⚠️ Please define at least one material in the 'Materials' tab first.")
        return
    
    # Show loaded sections management in edit mode
    if st.session_state.editing_mode and st.session_state.sections:
        # Track which sections have been confirmed/created in OpenSeesPy
        if 'confirmed_sections' not in st.session_state:
            st.session_state.confirmed_sections = set()
        if 'loaded_sections' not in st.session_state:
            st.session_state.loaded_sections = set()
        
        # Only show loaded sections that need confirmation
        loaded_sections_list = {name: props for name, props in st.session_state.sections.items() 
                               if name in st.session_state.get('loaded_sections', set())}
        
        if loaded_sections_list:
            st.markdown("---")
            st.subheader("📋 Manage Loaded Sections")
            st.info("⚠️ Loaded sections need to be confirmed to recreate them in OpenSeesPy. You can also edit or delete them.")
        
        for section_name, props in list(loaded_sections_list.items()):
            with st.expander(f"Section: **{section_name}** {'✅ Confirmed' if section_name in st.session_state.confirmed_sections else '⚠️ Not Confirmed'}", expanded=section_name not in st.session_state.confirmed_sections):
                col_info1, col_info2, col_info3 = st.columns(3)
                
                with col_info1:
                    st.write(f"**Dimensions:**")
                    st.write(f"- H: {props['H']:.3f} m")
                    st.write(f"- B: {props['B']:.3f} m")
                    st.write(f"- Cover: {props['cover']:.3f} m")
                    st.write(f"- Tag: {props['tag']}")
                
                with col_info2:
                    st.write(f"**Material:** {props['material']}")
                    st.write(f"**Reinforcement:**")
                    st.write(f"- Top: {props['bars_top']}x{props['area_top']}")
                    st.write(f"- Bottom: {props['bars_bottom']}x{props['area_bottom']}")
                    st.write(f"- Middle: {props['bars_middle']}x{props['area_middle']}")
                
                with col_info3:
                    st.write("**Actions:**")
                    
                    # Confirm button
                    if section_name not in st.session_state.confirmed_sections:
                        if st.button(f"✅ Confirm & Create", key=f"confirm_{section_name}", type="primary"):
                            try:
                                # Recreate the section in OpenSeesPy
                                selected_material = st.session_state.materials[props['material']]
                                bars_config = {
                                    'bars_top': props['bars_top'],
                                    'area_top': REBAR_AREAS[props['area_top']],
                                    'bars_bottom': props['bars_bottom'],
                                    'area_bottom': REBAR_AREAS[props['area_bottom']],
                                    'bars_middle': props['bars_middle'],
                                    'area_middle': REBAR_AREAS[props['area_middle']],
                                }
                                lib.create_section(props['tag'], props['H'], props['B'], props['cover'], selected_material, bars_config)
                                st.session_state.confirmed_sections.add(section_name)
                                st.success(f"✅ Section '{section_name}' created in OpenSeesPy!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Error creating section: {str(e)}")
                    else:
                        st.success("✅ Already confirmed")
                    
                    # Delete button
                    if st.button(f"🗑️ Delete", key=f"delete_{section_name}", type="secondary"):
                        del st.session_state.sections[section_name]
                        if section_name in st.session_state.confirmed_sections:
                            st.session_state.confirmed_sections.remove(section_name)
                        st.warning(f"⚠️ Section '{section_name}' deleted!")
                        st.rerun()
        
        # Confirm all button
        unconfirmed = [name for name in st.session_state.sections.keys() if name not in st.session_state.confirmed_sections]
        if unconfirmed:
            st.markdown("---")
            if st.button(f"✅ Confirm All {len(unconfirmed)} Unconfirmed Sections", type="primary", key="confirm_all_sections"):
                errors = []
                for section_name in unconfirmed:
                    try:
                        props = st.session_state.sections[section_name]
                        selected_material = st.session_state.materials[props['material']]
                        bars_config = {
                            'bars_top': props['bars_top'],
                            'area_top': REBAR_AREAS[props['area_top']],
                            'bars_bottom': props['bars_bottom'],
                            'area_bottom': REBAR_AREAS[props['area_bottom']],
                            'bars_middle': props['bars_middle'],
                            'area_middle': REBAR_AREAS[props['area_middle']],
                        }
                        lib.create_section(props['tag'], props['H'], props['B'], props['cover'], selected_material, bars_config)
                        st.session_state.confirmed_sections.add(section_name)
                    except Exception as e:
                        errors.append(f"{section_name}: {str(e)}")
                
                if not errors:
                    st.success(f"✅ All {len(unconfirmed)} sections confirmed and created in OpenSeesPy!")
                else:
                    st.error(f"❌ Errors occurred:\n" + "\n".join(errors))
                st.rerun()
        else:
            st.success("✅ All loaded sections have been confirmed!")
    
    st.markdown("---")
    st.subheader("➕ Add New Section")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        section_name = st.text_input(
            "Section Name",
            value="",
            placeholder="e.g., Col_55x55 or Beam_45x50",
            help="Enter a unique name for this section"
        )
        
        H_section = st.number_input(
            "H - Section Height (m)",
            min_value=0.10,
            max_value=5.0,
            value=0.55,
            step=0.05,
            format="%.3f",
            help="Height of the section"
        )
        
        B_section = st.number_input(
            "B - Section Base (m)",
            min_value=0.10,
            max_value=5.0,
            value=0.55,
            step=0.05,
            format="%.3f",
            help="Base width of the section"
        )
    
    with col2:
        cover = st.number_input(
            "c - Cover (m)",
            min_value=0.01,
            max_value=0.20,
            value=0.05,
            step=0.01,
            format="%.3f",
            help="Concrete cover"
        )
        
        material_name_select = st.selectbox(
            "Select Material",
            options=list(st.session_state.materials.keys()),
            help="Choose the material for this section"
        )
        
        st.markdown("**Top Reinforcement**")
        bars_top = st.number_input(
            "Number of bars (top)",
            min_value=1,
            max_value=20,
            value=5,
            step=1,
            help="Number of reinforcement bars at top"
        )
        
        area_top = st.selectbox(
            "Bar size (top)",
            options=list(REBAR_AREAS.keys()),
            index=4,  # As8
            help="Select rebar size for top bars"
        )
    
    with col3:
        st.markdown("**Bottom Reinforcement**")
        bars_bottom = st.number_input(
            "Number of bars (bottom)",
            min_value=1,
            max_value=20,
            value=5,
            step=1,
            help="Number of reinforcement bars at bottom"
        )
        
        area_bottom = st.selectbox(
            "Bar size (bottom)",
            options=list(REBAR_AREAS.keys()),
            index=4,  # As8
            help="Select rebar size for bottom bars"
        )
        
        st.markdown("**Middle Reinforcement**")
        bars_middle = st.number_input(
            "Number of bars (middle)",
            min_value=0,
            max_value=20,
            value=6,
            step=2,
            help="Number of reinforcement bars at middle (sides)"
        )
        
        area_middle = st.selectbox(
            "Bar size (middle)",
            options=list(REBAR_AREAS.keys()),
            index=4,  # As8
            help="Select rebar size for middle bars"
        )
    
    # Section preview visualization
    st.markdown("---")
    st.subheader("📐 Section Preview")
    
    try:
        section_fig = create_section_visualization(
            H_section, B_section, cover,
            bars_top, bars_bottom, bars_middle
        )
        st.plotly_chart(section_fig, use_container_width=True)
    except Exception as e:
        st.warning(f"Preview not available: {str(e)}")
    
    st.markdown("---")
    
    if st.button("Add Section", type="primary", key="add_section"):
        if section_name == "":
            st.error("⚠️ Please enter a section name")
        elif section_name in st.session_state.sections:
            st.error(f"⚠️ Section '{section_name}' already exists. Use a different name.")
        else:
            try:
                section_index = len(st.session_state.sections)
                section_tag = lib.generate_section_tag(section_index)
                
                selected_material = st.session_state.materials[material_name_select]
                
                bars_config = {
                    'bars_top': bars_top,
                    'area_top': REBAR_AREAS[area_top],
                    'bars_bottom': bars_bottom,
                    'area_bottom': REBAR_AREAS[area_bottom],
                    'bars_middle': bars_middle,
                    'area_middle': REBAR_AREAS[area_middle],
                }
                
                lib.create_section(section_tag, H_section, B_section, cover, selected_material, bars_config)
                
                st.session_state.sections[section_name] = {
                    'tag': section_tag,
                    'H': H_section,
                    'B': B_section,
                    'cover': cover,
                    'material': material_name_select,
                    'bars_top': bars_top,
                    'area_top': area_top,
                    'bars_bottom': bars_bottom,
                    'area_bottom': area_bottom,
                    'bars_middle': bars_middle,
                    'area_middle': area_middle
                }
                # Auto-confirm newly added sections (they were just created in OpenSeesPy)
                if 'confirmed_sections' not in st.session_state:
                    st.session_state.confirmed_sections = set()
                st.session_state.confirmed_sections.add(section_name)
                
                st.success(f"✅ Section '{section_name}' added successfully!")
                
            except Exception as e:
                st.error(f"❌ Error creating section: {str(e)}")
    
    # Display existing sections
    if st.session_state.sections:
        st.markdown("---")
        st.subheader("Defined Sections")
        
        sections_data = []
        for name, props in st.session_state.sections.items():
            sections_data.append({
                'Section Name': name,
                'Tag': props['tag'],
                'H (m)': f"{props['H']:.3f}",
                'B (m)': f"{props['B']:.3f}",
                'Cover (m)': f"{props['cover']:.3f}",
                'Material': props['material'],
                'Top Bars': f"{props['bars_top']}x{props['area_top']}",
                'Bottom Bars': f"{props['bars_bottom']}x{props['area_bottom']}",
                'Middle Bars': f"{props['bars_middle']}x{props['area_middle']}"
            })
        
        df_sections = pd.DataFrame(sections_data)
        st.dataframe(df_sections, use_container_width=True)
    else:
        st.info("ℹ️ No sections defined yet. Add your first section above.")


# ==================== ASSIGNMENT FUNCTIONS ====================
def initialize_floor_assignments(floor, n_positions, default_section):
    """Initialize assignments for a floor in 2D (simple list)"""
    return {pos: default_section for pos in range(n_positions)}


def copy_floor_assignments(source_floor, target_floors, assignments_dict):
    """Copy floor assignments to multiple target floors"""
    for target_floor in target_floors:
        assignments_dict[target_floor] = assignments_dict[source_floor].copy()


def build_element_tags_list_2d(assignments, sections, num_floors, num_positions):
    """
    Build list of section tags for 2D elements.
    
    Parameters:
    -----------
    assignments : dict
        {floor: {position: section_name}}
    sections : dict
        Section definitions
    num_floors : int
        Number of floors
    num_positions : int
        Number of positions (columns or beams)
    
    Returns:
    --------
    list : Nested list [floor][position] with section tags
    """
    tags_list = []
    for floor in range(1, num_floors + 1):
        floor_tags = []
        for pos in range(num_positions):
            section_name = assignments[floor][pos]
            if section_name == 'None' or section_name is None:
                floor_tags.append('None')
            else:
                floor_tags.append(sections[section_name]['tag'])
        tags_list.append(floor_tags)
    return tags_list


# ==================== VISUALIZATION FUNCTIONS ====================
def create_2d_frame_figure(coordx, coordy, column_assignments, beam_assignments, sections):
    """
    Create 2D frame elevation visualization with assigned sections.
    
    Parameters:
    -----------
    coordx : list
        X coordinates
    coordy : list
        Y coordinates
    column_assignments : dict
        {floor: {x_idx: section_name}}
    beam_assignments : dict
        {floor: {span_idx: section_name}}
    sections : dict
        Section definitions
    
    Returns:
    --------
    plotly.graph_objects.Figure
    """
    fig = go.Figure()
    
    # Generate unique colors for each section - use all unique sections from assignments
    section_names = list(set([
        s for floor_dict in column_assignments.values() for s in floor_dict.values() if s and s != 'None'
    ] + [
        s for floor_dict in beam_assignments.values() for s in floor_dict.values() if s and s != 'None'
    ]))
    
    # Extended color palette for better distinction
    colors = ['#e6194b', '#3cb44b', '#ffe119', '#4363d8', '#f58231', 
              '#911eb4', '#46f0f0', '#f032e6', '#bcf60c', '#fabebe',
              '#008080', '#e6beff', '#9a6324', '#fffac8', '#800000',
              '#aaffc3', '#808000', '#ffd8b1', '#000075', '#808080']
    section_colors = {name: colors[i % len(colors)] for i, name in enumerate(section_names)}
    
    # Track which sections have been added to legend
    legend_added = set()
    
    n_floors = len(coordy) - 1
    n_x = len(coordx)
    n_spans = len(coordx) - 1
    
    # Draw columns
    for floor in range(1, n_floors + 1):
        y_bot = coordy[floor - 1]
        y_top = coordy[floor]
        
        for x_idx in range(n_x):
            x = coordx[x_idx]
            section_name = column_assignments.get(floor, {}).get(x_idx, 'None')
            
            if section_name and section_name != 'None':
                color = section_colors.get(section_name, 'black')
                section_props = sections[section_name]
                
                # Show in legend only once per section
                show_legend = section_name not in legend_added
                if show_legend:
                    legend_added.add(section_name)
                
                fig.add_trace(go.Scatter(
                    x=[x, x],
                    y=[y_bot, y_top],
                    mode='lines',
                    line=dict(color=color, width=4),
                    name=section_name,
                    showlegend=show_legend,
                    legendgroup=section_name,
                    hovertemplate=(
                        f'<b>Column</b><br>'
                        f'Floor: {floor}<br>'
                        f'X: {x:.2f}m<br>'
                        f'Section: {section_name}<br>'
                        f'H×B: {section_props["H"]*1000:.0f}×{section_props["B"]*1000:.0f}mm<br>'
                        f'Material: {section_props["material"]}<br>'
                        '<extra></extra>'
                    )
                ))
    
    # Draw beams
    for floor in range(1, n_floors + 1):
        y = coordy[floor]
        
        for span_idx in range(n_spans):
            x1 = coordx[span_idx]
            x2 = coordx[span_idx + 1]
            section_name = beam_assignments.get(floor, {}).get(span_idx, 'None')
            
            if section_name and section_name != 'None':
                color = section_colors.get(section_name, 'black')
                section_props = sections[section_name]
                
                # Show in legend only once per section
                show_legend = section_name not in legend_added
                if show_legend:
                    legend_added.add(section_name)
                
                fig.add_trace(go.Scatter(
                    x=[x1, x2],
                    y=[y, y],
                    mode='lines',
                    line=dict(color=color, width=4),
                    name=section_name,
                    showlegend=show_legend,
                    legendgroup=section_name,
                    hovertemplate=(
                        f'<b>Beam</b><br>'
                        f'Floor: {floor}<br>'
                        f'Span: {x1:.2f}m → {x2:.2f}m<br>'
                        f'Section: {section_name}<br>'
                        f'H×B: {section_props["H"]*1000:.0f}×{section_props["B"]*1000:.0f}mm<br>'
                        f'Material: {section_props["material"]}<br>'
                        '<extra></extra>'
                    )
                ))
    
    # Draw nodes
    for x in coordx:
        for y in coordy:
            fig.add_trace(go.Scatter(
                x=[x], y=[y],
                mode='markers',
                marker=dict(size=6, color='black', symbol='circle'),
                showlegend=False,
                hovertemplate=f'Node<br>X: {x:.2f}m<br>Y: {y:.2f}m<extra></extra>'
            ))
    
    # Update layout
    fig.update_layout(
        title="2D Frame Elevation",
        xaxis_title="X Coordinate (m)",
        yaxis_title="Y Coordinate (m)",
        height=600,
        hovermode='closest',
        showlegend=True,
        legend=dict(x=1.05, y=1, xanchor='left'),
        plot_bgcolor='white',
        xaxis=dict(showgrid=True, gridcolor='lightgray', zeroline=True),
        yaxis=dict(showgrid=True, gridcolor='lightgray', zeroline=True, scaleanchor='x', scaleratio=1)
    )
    
    return fig


# ==================== TAB 4: ELEMENT ASSIGNMENT ====================
def render_assignment_tab():
    """Render Element Assignment tab for 2D model"""
    st.header("Element Assignment")
    st.markdown("Assign sections to columns and beams for each floor.")
    
    if not st.session_state.model_created:
        st.warning("⚠️ Please create the model in the 'Building Geometry' tab first.")
        return
    elif not st.session_state.sections:
        st.warning("⚠️ Please define at least one section in the 'Sections' tab first.")
        return
    
    # Get building dimensions
    n_floors = len(st.session_state.coordy) - 1
    n_x_positions = len(st.session_state.coordx)
    n_spans = len(st.session_state.coordx) - 1
    
    # Include 'None' as an option for elements without sections (like in master_script)
    section_names = ['None'] + list(st.session_state.sections.keys())
    
    # Initialize assignments if not exists
    for floor in range(1, n_floors + 1):
        if floor not in st.session_state.column_assignments:
            st.session_state.column_assignments[floor] = {x_idx: section_names[1] for x_idx in range(n_x_positions)}
        
        if floor not in st.session_state.beam_assignments:
            st.session_state.beam_assignments[floor] = {span_idx: section_names[1] for span_idx in range(n_spans)}
    
    # Create two-column layout: controls on left, visualization on right
    col_controls, col_viz = st.columns([1, 2])
    
    with col_controls:
        st.subheader("⚙️ Assignment Controls")
        
        # Element type selector
        element_type = st.radio(
            "Select Element Type:",
            options=['Columns', 'Beams'],
            key='element_type_selector_2d'
        )
        
        # Floor selector
        selected_floors = st.multiselect(
            "Select Floor(s):",
            options=list(range(1, n_floors + 1)),
            default=[1],
            format_func=lambda x: f"Floor {x}",
            key='floor_selector_2d'
        )
        
        st.markdown("---")
        
        # Section selector
        st.markdown("**Assign Section:**")
        selected_section = st.selectbox(
            "Choose section to assign:",
            options=section_names,
            help="Select 'None' to create elements without sections (element will not be created)",
            key='section_selector_2d'
        )
        
        # Show section properties
        if selected_section and selected_section != 'None':
            with st.expander("📋 Section Details", expanded=False):
                props = st.session_state.sections[selected_section]
                st.write(f"**Dimensions:** {props['H']*1000:.0f} × {props['B']*1000:.0f} mm")
                st.write(f"**Material:** {props['material']}")
                st.write(f"**Reinforcement:**")
                st.write(f"  - Top: {props['bars_top']}×{props['area_top']}")
                st.write(f"  - Bottom: {props['bars_bottom']}×{props['area_bottom']}")
                st.write(f"  - Sides: {props['bars_middle']}×{props['area_middle']}")
        
        st.markdown("---")
        
        # Assignment method selector
        st.markdown("**Assignment Method:**")
        assign_method = st.radio(
            "Select method:",
            options=['Assign All', 'By Position'],
            key='assign_method_2d'
        )
        
        if assign_method == 'Assign All':
            st.info(f"This will assign **{selected_section}** to ALL {element_type.lower()} on the selected floor(s).")
            
            if st.button("🎯 Assign to All", type="primary", key='assign_all_button_2d'):
                if not selected_floors:
                    st.error("⚠️ Please select at least one floor.")
                else:
                    count = 0
                    for floor in selected_floors:
                        if element_type == 'Columns':
                            for x_idx in range(n_x_positions):
                                st.session_state.column_assignments[floor][x_idx] = selected_section
                                count += 1
                        else:  # Beams
                            for span_idx in range(n_spans):
                                st.session_state.beam_assignments[floor][span_idx] = selected_section
                                count += 1
                    
                    st.success(f"✅ Assigned **{selected_section}** to {count} elements!")
                    st.rerun()
        
        else:  # By Position
            st.info("Select specific positions to assign the section.")
            
            if element_type == 'Columns':
                st.markdown("**Column Position:**")
                col_x_idx = st.selectbox(
                    "X Position:", 
                    options=list(range(n_x_positions)),
                    format_func=lambda i: f"X{i+1} ({st.session_state.coordx[i]:.2f} m)"
                )
                
                if st.button("🎯 Assign to Selected Column", type="primary", key='assign_column_button_2d'):
                    if not selected_floors:
                        st.error("⚠️ Please select at least one floor.")
                    else:
                        for floor in selected_floors:
                            st.session_state.column_assignments[floor][col_x_idx] = selected_section
                        st.success(f"✅ Assigned to column at X{col_x_idx+1} on {len(selected_floors)} floor(s)!")
                        st.rerun()
            
            else:  # Beams
                st.markdown("**Beam Position:**")
                beam_span_idx = st.selectbox(
                    "Span:", 
                    options=list(range(n_spans)),
                    format_func=lambda i: f"Span {i+1} ({st.session_state.coordx[i]:.2f}→{st.session_state.coordx[i+1]:.2f} m)"
                )
                
                if st.button("🎯 Assign to Selected Beam", type="primary", key='assign_beam_button_2d'):
                    if not selected_floors:
                        st.error("⚠️ Please select at least one floor.")
                    else:
                        for floor in selected_floors:
                            st.session_state.beam_assignments[floor][beam_span_idx] = selected_section
                        st.success(f"✅ Assigned to beam span {beam_span_idx+1} on {len(selected_floors)} floor(s)!")
                        st.rerun()
        
        st.markdown("---")
        
        # Copy configuration tool
        st.markdown("**🔄 Copy Floor Configuration:**")
        copy_source_floor = st.selectbox(
            "Copy from Floor:",
            options=list(range(1, n_floors + 1)),
            format_func=lambda x: f"Floor {x}",
            key='copy_source_floor_2d'
        )
        
        copy_to_floors = st.multiselect(
            "Copy to Floor(s):",
            options=[f for f in range(1, n_floors + 1) if f != copy_source_floor],
            format_func=lambda x: f"Floor {x}",
            key='copy_to_floors_2d'
        )
        
        if st.button("📋 Copy Configuration", type="secondary", key='copy_config_2d'):
            if not copy_to_floors:
                st.error("⚠️ Please select at least one target floor.")
            else:
                for target_floor in copy_to_floors:
                    st.session_state.column_assignments[target_floor] = st.session_state.column_assignments[copy_source_floor].copy()
                    st.session_state.beam_assignments[target_floor] = st.session_state.beam_assignments[copy_source_floor].copy()
                st.success(f"✅ Configuration copied from Floor {copy_source_floor} to {len(copy_to_floors)} floor(s)!")
                st.rerun()
        
        st.markdown("---")
        
        # Quick statistics
        st.markdown("**📊 Assignment Summary:**")
        total_cols = n_x_positions * n_floors
        total_beams = n_spans * n_floors
        
        st.metric("Total Columns", total_cols)
        st.metric("Total Beams", total_beams)
    
    with col_viz:
        st.subheader("🏗️ 2D Frame Visualization")
        
        # Create and display 2D visualization
        try:
            frame_fig = lib.create_2d_frame_figure(
                st.session_state.coordx,
                st.session_state.coordy,
                st.session_state.column_assignments,
                st.session_state.beam_assignments,
                st.session_state.sections
            )
            st.plotly_chart(frame_fig, use_container_width=True, key="assignment_tab_viz")
        except Exception as e:
            st.error(f"❌ Error creating visualization: {str(e)}")
            st.code(str(e))


# ==================== TAB 5: MODEL VISUALIZATION ====================
def render_model_visualization_tab():
    """Render Model Visualization and Element Creation tab"""
    st.header("Model Visualization & Element Creation")
    st.markdown("Review the complete structural model and create OpenSeesPy elements.")
    
    if not st.session_state.model_created:
        st.warning("⚠️ Please create the model first.")
        return
    elif not st.session_state.sections:
        st.warning("⚠️ Please define sections first.")
        return
    
    # Check if materials and sections are confirmed in edit mode
    if st.session_state.editing_mode:
        unconfirmed_materials = [name for name in st.session_state.materials.keys() 
                                if name not in st.session_state.get('confirmed_materials', set())]
        unconfirmed_sections = [name for name in st.session_state.sections.keys() 
                               if name not in st.session_state.get('confirmed_sections', set())]
        
        if unconfirmed_materials or unconfirmed_sections:
            st.error("⚠️ **Cannot create elements yet!** Please confirm all loaded materials and sections first.")
            if unconfirmed_materials:
                st.warning(f"📋 Unconfirmed Materials ({len(unconfirmed_materials)}): {', '.join(unconfirmed_materials)}")
                st.info("👉 Go to the 'Materials' tab and click 'Confirm & Create' for each material, or use 'Confirm All'.")
            if unconfirmed_sections:
                st.warning(f"📋 Unconfirmed Sections ({len(unconfirmed_sections)}): {', '.join(unconfirmed_sections)}")
                st.info("👉 Go to the 'Sections' tab and click 'Confirm & Create' for each section, or use 'Confirm All'.")
            return
        else:
            st.success("✅ All materials and sections have been confirmed in OpenSeesPy!")
    
    # Check if all assignments are complete
    n_floors = len(st.session_state.coordy) - 1
    all_columns_configured = all(f in st.session_state.column_assignments for f in range(1, n_floors + 1))
    all_beams_configured = all(f in st.session_state.beam_assignments for f in range(1, n_floors + 1))
    
    if not (all_columns_configured and all_beams_configured):
        st.warning("⚠️ Please complete all column and beam assignments before creating elements.")
        return
    
    st.success("✅ All assignments complete!")
    
    # Create visualization
    st.subheader("🏗️ 2D Frame Model")
    
    try:
        fig = lib.create_2d_frame_figure(
            st.session_state.coordx,
            st.session_state.coordy,
            st.session_state.column_assignments,
            st.session_state.beam_assignments,
            st.session_state.sections
        )
        st.plotly_chart(fig, use_container_width=True, key="model_viz_tab")
    except Exception as e:
        st.error(f"❌ Error creating visualization: {str(e)}")
    
    # Create elements
    st.markdown("---")
    st.subheader("Create Structural Elements")
    
    if st.session_state.elements_created:
        st.success("✅ Elements have been created successfully!")
        
        # Show element summary
        col_sum1, col_sum2, col_sum3 = st.columns(3)
        with col_sum1:
            st.metric("Total Columns", len(st.session_state.tagcols) if st.session_state.tagcols else 0)
        with col_sum2:
            st.metric("Total Beams", len(st.session_state.tagbeams) if st.session_state.tagbeams else 0)
        with col_sum3:
            diaphragm_count = sum(st.session_state.get('floor_diaphragms', []))
            st.metric("Floors with Diaphragms", diaphragm_count)
        
        # Show which floors have diaphragms
        if 'floor_diaphragms' in st.session_state:
            with st.expander("📋 Diaphragm Configuration"):
                diaphragm_floors = [f+1 for f, val in enumerate(st.session_state.floor_diaphragms) if val == 1]
                if diaphragm_floors:
                    st.write(f"**Floors with rigid diaphragms:** {', '.join(map(str, diaphragm_floors))}")
                else:
                    st.write("**No rigid diaphragms applied**")
    else:
        st.markdown("#### Diaphragm Configuration")
        st.info("🔗 **Rigid diaphragms** constrain all nodes at a floor level to move together horizontally. This is typical for floors with concrete slabs.")
        
        # Diaphragm selection options
        diaphragm_mode = st.radio(
            "Select diaphragm configuration:",
            options=['All Floors', 'Custom Selection', 'No Diaphragms'],
            index=0,
            help="Choose which floors should have rigid diaphragm constraints"
        )
        
        selected_diaphragm_floors = []
        
        if diaphragm_mode == 'All Floors':
            st.success(f"✅ Rigid diaphragms will be applied to all {n_floors} floors")
            selected_diaphragm_floors = list(range(1, n_floors + 1))
        elif diaphragm_mode == 'Custom Selection':
            st.markdown("**Select floors for rigid diaphragm:**")
            selected_diaphragm_floors = st.multiselect(
                "Choose floors:",
                options=list(range(1, n_floors + 1)),
                default=list(range(1, n_floors + 1)),
                format_func=lambda x: f"Floor {x}",
                help="Select which floors should have rigid diaphragm constraints"
            )
            if selected_diaphragm_floors:
                st.info(f"🔗 Diaphragms will be applied to {len(selected_diaphragm_floors)} floor(s): {', '.join(map(str, selected_diaphragm_floors))}")
            else:
                st.warning("⚠️ No floors selected - no diaphragms will be applied")
        else:  # No Diaphragms
            st.warning("⚠️ No rigid diaphragms will be applied to any floor")
            selected_diaphragm_floors = []
        
        st.markdown("---")
        
        create_button_label = "🔄 Recreate Elements" if st.session_state.elements_created else "🏗️ Create Elements"
        if st.button(create_button_label, type="primary", key="create_elements_button_2d"):
            try:
                with st.spinner("Creating structural elements..."):
                    n_x_positions = len(st.session_state.coordx)
                    n_spans = len(st.session_state.coordx) - 1
                    
                    # Build tag lists for 2D
                    building_columns = lib.build_element_tags_list_2d(
                        st.session_state.column_assignments,
                        st.session_state.sections,
                        n_floors,
                        n_x_positions
                    )
                    
                    building_beams = lib.build_element_tags_list_2d(
                        st.session_state.beam_assignments,
                        st.session_state.sections,
                        n_floors,
                        n_spans
                    )
                    
                    # Debug output - show what's being passed to ut.create_elements2
                    st.info("🐛 **Debug: Element Creation Parameters**")
                    st.write(f"**coordx:** {st.session_state.coordx}")
                    st.write(f"**coordy:** {st.session_state.coordy}")
                    st.write(f"**building_columns (by floor):**")
                    for i, floor_cols in enumerate(building_columns):
                        st.write(f"  Floor {i+1}: {floor_cols}")
                    st.write(f"**building_beams (by floor):**")
                    for i, floor_beams in enumerate(building_beams):
                        st.write(f"  Floor {i+1}: {floor_beams}")
                    
                    # Create 2D elements using opseestools
                    tagcols, tagbeams, column_info, beam_info = ut.create_elements2(
                        st.session_state.coordx,
                        st.session_state.coordy,
                        building_columns,
                        building_beams,
                        output=1
                    )
                    
                    st.write(f"**tagcols returned (first 10):** {tagcols[:10]}")
                    st.write(f"**tagbeams returned (first 10):** {tagbeams[:10]}")
                    
                    # Remove hanging nodes
                    ut.remove_hanging_nodes(tagcols, tagbeams)
                    
                    # Apply diaphragms based on user selection
                    # Create floor_diaphragms list: 1 for floors with diaphragm, 0 for floors without
                    floor_diaphragms = [1 if (f+1) in selected_diaphragm_floors else 0 for f in range(n_floors)]
                    
                    st.write(f"**floor_diaphragms:** {floor_diaphragms}")
                    
                    if sum(floor_diaphragms) > 0:
                        ut.apply_diaphragms(floor_diaphragms, output=1)
                    
                    # Store in session state - ensure all tags are integers
                    st.session_state.tagcols = [int(tag) for tag in tagcols]
                    st.session_state.tagbeams = [int(tag) for tag in tagbeams]
                    st.session_state.column_info = column_info
                    st.session_state.beam_info = beam_info
                    st.session_state.elements_created = True
                    # Store node tags for infill panel validity checks
                    st.session_state.model_node_tags = [int(n) for n in getNodeTags()]
                    # Reset loads and infills flags when elements are recreated
                    st.session_state.loads_applied = False
                    st.session_state.infills_assigned = False
                    st.session_state.floor_diaphragms = floor_diaphragms
                    
                    st.success("✅ Elements created successfully!")
                    st.success(f"📊 Created {len(tagcols)} columns and {len(tagbeams)} beams")
                    if sum(floor_diaphragms) > 0:
                        st.success(f"🔗 Applied rigid diaphragm constraints to {sum(floor_diaphragms)} floor(s)")
                    else:
                        st.info("ℹ️ No rigid diaphragm constraints applied")
                    st.rerun()
                    
            except Exception as e:
                st.error(f"❌ Error creating elements: {str(e)}")
                import traceback
                st.code(traceback.format_exc())


# ==================== TAB: INFILL ASSIGNMENT ====================
def get_valid_panels(coordx, coordy, model_node_tags):
    """
    Determine which panels are valid for infill placement.
    A panel is valid if all 4 corner nodes exist in the model after hanging node removal.

    Returns a dict: {floor: {span: True/False}}
    """
    n_floors = len(coordy) - 1
    n_spans = len(coordx) - 1
    valid = {}
    node_set = set(model_node_tags)

    for f in range(1, n_floors + 1):
        valid[f] = {}
        for s in range(n_spans):
            # Node numbering: 1000*(x_idx+1) + y_idx
            # Bottom-left: x_idx=s, y_idx=f-1
            # Bottom-right: x_idx=s+1, y_idx=f-1
            # Top-left: x_idx=s, y_idx=f
            # Top-right: x_idx=s+1, y_idx=f
            n_bl = 1000 * (s + 1) + (f - 1)
            n_br = 1000 * (s + 2) + (f - 1)
            n_tl = 1000 * (s + 1) + f
            n_tr = 1000 * (s + 2) + f
            valid[f][s] = all(n in node_set for n in [n_bl, n_br, n_tl, n_tr])

    return valid


def create_infill_frame_figure(coordx, coordy, column_assignments, beam_assignments,
                               sections, infill_assignments, valid_panels, masonry_materials):
    """
    Create 2D frame figure with infill panels visualized.
    Assigned infills: shaded rectangle + X-pattern.
    Valid but unassigned: dashed outline.
    Invalid: not shown.
    """
    # Start with the base frame figure
    fig = lib.create_2d_frame_figure(coordx, coordy, column_assignments, beam_assignments, sections)

    n_floors = len(coordy) - 1
    n_spans = len(coordx) - 1

    # Color palette for different masonry materials
    mas_colors = ['rgba(255,165,0,0.3)', 'rgba(139,69,19,0.3)', 'rgba(210,105,30,0.3)',
                  'rgba(244,164,96,0.3)', 'rgba(188,143,143,0.3)']
    mas_line_colors = ['rgba(255,140,0,0.8)', 'rgba(139,69,19,0.8)', 'rgba(210,105,30,0.8)',
                       'rgba(244,164,96,0.8)', 'rgba(188,143,143,0.8)']
    mas_names = list(masonry_materials.keys())
    mas_color_map = {name: mas_colors[i % len(mas_colors)] for i, name in enumerate(mas_names)}
    mas_line_map = {name: mas_line_colors[i % len(mas_line_colors)] for i, name in enumerate(mas_names)}

    legend_added_infill = set()

    for f in range(1, n_floors + 1):
        y_bot = coordy[f - 1]
        y_top = coordy[f]

        for s in range(n_spans):
            x_left = coordx[s]
            x_right = coordx[s + 1]

            if not valid_panels.get(f, {}).get(s, False):
                continue  # Invalid panel, skip

            assignment = infill_assignments.get(f, {}).get(s, {})
            mat_name = assignment.get('material_name', 'None')

            if mat_name and mat_name != 'None':
                fill_color = mas_color_map.get(mat_name, 'rgba(255,165,0,0.3)')
                line_color = mas_line_map.get(mat_name, 'rgba(255,140,0,0.8)')
                thickness = assignment.get('thickness', 0.1)
                show_legend = mat_name not in legend_added_infill

                # Shaded rectangle
                fig.add_trace(go.Scatter(
                    x=[x_left, x_right, x_right, x_left, x_left],
                    y=[y_bot, y_bot, y_top, y_top, y_bot],
                    fill='toself',
                    fillcolor=fill_color,
                    line=dict(color=line_color, width=1),
                    mode='lines',
                    name=f'Infill: {mat_name}',
                    legendgroup=f'infill_{mat_name}',
                    showlegend=show_legend,
                    hovertemplate=f'Infill<br>Material: {mat_name}<br>Floor: {f}<br>Span: {s+1}<br>Thickness: {thickness}m<extra></extra>'
                ))

                # X-pattern diagonal lines
                fig.add_trace(go.Scatter(
                    x=[x_left, x_right], y=[y_bot, y_top],
                    mode='lines',
                    line=dict(color=line_color, width=2, dash='solid'),
                    showlegend=False,
                    legendgroup=f'infill_{mat_name}',
                    hoverinfo='skip'
                ))
                fig.add_trace(go.Scatter(
                    x=[x_left, x_right], y=[y_top, y_bot],
                    mode='lines',
                    line=dict(color=line_color, width=2, dash='solid'),
                    showlegend=False,
                    legendgroup=f'infill_{mat_name}',
                    hoverinfo='skip'
                ))

                if show_legend:
                    legend_added_infill.add(mat_name)
            else:
                # Valid but unassigned - dashed outline
                fig.add_trace(go.Scatter(
                    x=[x_left, x_right, x_right, x_left, x_left],
                    y=[y_bot, y_bot, y_top, y_top, y_bot],
                    fill=None,
                    line=dict(color='rgba(200,200,200,0.5)', width=1, dash='dash'),
                    mode='lines',
                    showlegend=False,
                    hovertemplate=f'Available Panel<br>Floor: {f}<br>Span: {s+1}<extra></extra>'
                ))

    return fig


def render_infill_assignment_tab():
    """Render Infill Assignment tab for defining masonry infill walls."""
    st.header("Infill Wall Assignment")
    st.markdown("Assign masonry infill walls to panels in the building frame.")

    if not st.session_state.elements_created or st.session_state.model_node_tags is None:
        st.warning("⚠️ Please create structural elements in the 'Model Visualization' tab first.")
        return

    if not st.session_state.masonry_materials:
        st.warning("⚠️ Please define at least one masonry material in the 'Masonry Materials' tab first.")
        return

    n_floors = len(st.session_state.coordy) - 1
    n_spans = len(st.session_state.coordx) - 1

    # Determine valid panels
    valid_panels = get_valid_panels(
        st.session_state.coordx,
        st.session_state.coordy,
        st.session_state.model_node_tags
    )

    # Initialize infill_assignments if empty
    if not st.session_state.infill_assignments:
        for f in range(1, n_floors + 1):
            st.session_state.infill_assignments[f] = {}
            for s in range(n_spans):
                st.session_state.infill_assignments[f][s] = {
                    'thickness': 0.1,
                    'material_name': 'None'
                }

    # Two-column layout: controls on left, visualization on right
    col_controls, col_viz = st.columns([1, 2])

    with col_controls:
        st.subheader("⚙️ Infill Controls")

        # Global width percentage
        st.session_state.width_percentage = st.number_input(
            "Width Percentage (w/d ratio)",
            min_value=0.05,
            max_value=0.50,
            value=st.session_state.width_percentage,
            step=0.05,
            help="Ratio of equivalent strut width to diagonal length. Priestley: 0.25 (d/4), Borah: 0.33 (d/3)",
            key="width_pct_input"
        )

        st.markdown("---")

        # Floor selector
        selected_floors = st.multiselect(
            "Select Floor(s):",
            options=list(range(1, n_floors + 1)),
            default=[1],
            format_func=lambda x: f"Floor {x}",
            key='infill_floor_selector'
        )

        st.markdown("---")

        # Material selector
        masonry_names = list(st.session_state.masonry_materials.keys())
        material_options = ['None'] + masonry_names
        selected_material = st.selectbox(
            "Masonry Material:",
            options=material_options,
            help="Select 'None' to remove infill from the panel",
            key='infill_material_selector'
        )

        # Show material properties
        if selected_material and selected_material != 'None':
            props = st.session_state.masonry_materials[selected_material]
            with st.expander("📋 Material Details", expanded=False):
                st.write(f"**f'm:** {props['fm']} MPa")
                st.write(f"**Brick Type:** {props['brick_type']}")
                st.write(f"**Tag:** {props['tag']}")

        # Thickness input
        thickness_input = st.number_input(
            "Brick Thickness (m)",
            min_value=0.01,
            max_value=0.50,
            value=0.10,
            step=0.01,
            help="Thickness of the infill wall in meters",
            key='infill_thickness_input'
        )

        st.markdown("---")

        # Assignment method
        assign_method = st.radio(
            "Assignment Method:",
            options=['Assign All Spans', 'By Span'],
            key='infill_assign_method'
        )

        if assign_method == 'Assign All Spans':
            st.info(f"Assign to ALL valid spans on selected floor(s).")

            if st.button("🎯 Assign Infills", type="primary", key='assign_all_infills'):
                if not selected_floors:
                    st.error("⚠️ Please select at least one floor.")
                else:
                    count = 0
                    for floor in selected_floors:
                        for span in range(n_spans):
                            if valid_panels.get(floor, {}).get(span, False):
                                st.session_state.infill_assignments[floor][span] = {
                                    'thickness': thickness_input,
                                    'material_name': selected_material
                                }
                                count += 1
                    st.success(f"✅ Assigned infills to {count} panels!")
                    st.rerun()

        else:  # By Span
            span_options = []
            for s in range(n_spans):
                # Show only valid spans for the first selected floor
                label = f"Span {s+1} ({st.session_state.coordx[s]:.2f}→{st.session_state.coordx[s+1]:.2f} m)"
                span_options.append(s)

            selected_span = st.selectbox(
                "Span:",
                options=span_options,
                format_func=lambda i: f"Span {i+1} ({st.session_state.coordx[i]:.2f}→{st.session_state.coordx[i+1]:.2f} m)",
                key='infill_span_selector'
            )

            if st.button("🎯 Assign to Span", type="primary", key='assign_span_infill'):
                if not selected_floors:
                    st.error("⚠️ Please select at least one floor.")
                else:
                    count = 0
                    for floor in selected_floors:
                        if valid_panels.get(floor, {}).get(selected_span, False):
                            st.session_state.infill_assignments[floor][selected_span] = {
                                'thickness': thickness_input,
                                'material_name': selected_material
                            }
                            count += 1
                        else:
                            st.warning(f"⚠️ Panel at Floor {floor}, Span {selected_span+1} is not valid (missing nodes).")
                    if count > 0:
                        st.success(f"✅ Assigned infills to {count} panels!")
                        st.rerun()

        st.markdown("---")

        # Clear floor
        if st.button("🗑️ Clear Selected Floors", key='clear_infill_floors'):
            if selected_floors:
                for floor in selected_floors:
                    for span in range(n_spans):
                        st.session_state.infill_assignments[floor][span] = {
                            'thickness': 0.1,
                            'material_name': 'None'
                        }
                st.success(f"✅ Cleared infills on {len(selected_floors)} floor(s).")
                st.rerun()

        st.markdown("---")

        # Copy floor configuration
        st.markdown("**🔄 Copy Floor Configuration:**")
        copy_source = st.selectbox(
            "Copy from Floor:",
            options=list(range(1, n_floors + 1)),
            format_func=lambda x: f"Floor {x}",
            key='infill_copy_source'
        )
        copy_targets = st.multiselect(
            "Copy to Floor(s):",
            options=[f for f in range(1, n_floors + 1) if f != copy_source],
            format_func=lambda x: f"Floor {x}",
            key='infill_copy_targets'
        )
        if st.button("📋 Copy Configuration", type="secondary", key='copy_infill_config'):
            if not copy_targets:
                st.error("⚠️ Please select at least one target floor.")
            else:
                for target in copy_targets:
                    for span in range(n_spans):
                        if valid_panels.get(target, {}).get(span, False):
                            source_data = st.session_state.infill_assignments.get(copy_source, {}).get(span, {})
                            st.session_state.infill_assignments[target][span] = source_data.copy()
                        else:
                            st.session_state.infill_assignments[target][span] = {
                                'thickness': 0.1,
                                'material_name': 'None'
                            }
                st.success(f"✅ Copied from Floor {copy_source} to {len(copy_targets)} floor(s)!")
                st.rerun()

        st.markdown("---")

        # Assignment summary
        st.markdown("**📊 Infill Summary:**")
        total_valid = sum(1 for f in valid_panels for s in valid_panels[f] if valid_panels[f][s])
        total_assigned = sum(
            1 for f in st.session_state.infill_assignments
            for s in st.session_state.infill_assignments[f]
            if st.session_state.infill_assignments[f][s].get('material_name', 'None') != 'None'
        )
        st.metric("Valid Panels", total_valid)
        st.metric("Assigned Infills", total_assigned)

    with col_viz:
        st.subheader("🏗️ Frame with Infills")

        try:
            fig = create_infill_frame_figure(
                st.session_state.coordx,
                st.session_state.coordy,
                st.session_state.column_assignments,
                st.session_state.beam_assignments,
                st.session_state.sections,
                st.session_state.infill_assignments,
                valid_panels,
                st.session_state.masonry_materials
            )
            st.plotly_chart(fig, use_container_width=True, key="infill_viz")
        except Exception as e:
            st.error(f"❌ Error creating visualization: {str(e)}")

        # Current assignments table
        with st.expander("📋 Current Infill Assignments", expanded=False):
            table_data = []
            for f in range(1, n_floors + 1):
                for s in range(n_spans):
                    is_valid = valid_panels.get(f, {}).get(s, False)
                    assignment = st.session_state.infill_assignments.get(f, {}).get(s, {})
                    mat_name = assignment.get('material_name', 'None')
                    thickness = assignment.get('thickness', 0.1)
                    table_data.append({
                        'Floor': f,
                        'Span': s + 1,
                        'Valid': '✅' if is_valid else '❌',
                        'Material': mat_name if is_valid else 'N/A',
                        'Thickness (m)': thickness if is_valid and mat_name != 'None' else '-',
                    })
            df_infill = pd.DataFrame(table_data)
            st.dataframe(df_infill, use_container_width=True)

    # --- Apply Infills Button ---
    st.markdown("---")
    st.subheader("Apply Infill Elements")

    if st.session_state.infills_assigned:
        st.success("✅ Infill elements have been applied to the model!")
    else:
        st.info("Once you have finished assigning infills, click the button below to create the truss elements in the OpenSeesPy model.")

        if st.button("🧱 Apply Infills to Model", type="primary", key="apply_infills_button"):
            try:
                with st.spinner("Creating infill truss elements..."):
                    # Recreate masonry materials in OpenSeesPy (in case model was reloaded/wiped)
                    for mas_name, mas_props in st.session_state.masonry_materials.items():
                        try:
                            lib.col_infill(mas_props['fm'], mas_props['tag'], mas_props['brick_type'])
                        except Exception:
                            pass  # Material already exists in OpenSeesPy

                    negligible_thickness = 1e-10
                    diagonal_pairs = st.session_state.diagonal_pairs
                    diagonal_lengths = st.session_state.diagonal_lengths
                    width_percentage = st.session_state.width_percentage

                    # Compute widths
                    building_infill_widths = lib.infill_widths(diagonal_lengths, width_percentage)

                    # Build thickness and material lists from assignments
                    building_infill_thickness = []
                    building_infill_materials = []

                    for f in range(1, n_floors + 1):
                        floor_thickness = []
                        floor_materials = []
                        for s in range(n_spans):
                            is_valid = valid_panels.get(f, {}).get(s, False)
                            assignment = st.session_state.infill_assignments.get(f, {}).get(s, {})
                            mat_name = assignment.get('material_name', 'None')

                            if is_valid and mat_name != 'None':
                                floor_thickness.append(assignment.get('thickness', 0.1))
                                # Look up the material tag
                                mat_tag = st.session_state.masonry_materials[mat_name]['tag']
                                floor_materials.append(mat_tag)
                            else:
                                floor_thickness.append(negligible_thickness)
                                floor_materials.append('None')

                        building_infill_thickness.append(floor_thickness)
                        building_infill_materials.append(floor_materials)

                    # Compute areas
                    building_infill_areas = (
                        np.array(building_infill_thickness) * np.array(building_infill_widths)
                    ).tolist()

                    # Create truss elements
                    lib.assign_infills(diagonal_pairs, building_infill_areas, building_infill_materials)

                    st.session_state.infills_assigned = True
                    st.success("✅ Infill truss elements created successfully!")

                    total_infills = sum(
                        1 for floor_mats in building_infill_materials
                        for mat in floor_mats if mat != 'None'
                    )
                    st.success(f"📊 Created {total_infills * 2} truss elements ({total_infills} panels × 2 diagonals)")
                    st.rerun()

            except Exception as e:
                st.error(f"❌ Error creating infill elements: {str(e)}")
                import traceback
                st.code(traceback.format_exc())


# ==================== TAB 6: LOADS ====================
def render_loads_and_masses_tab():
    """Render Loads and Mass Assignments tab for 2D model with sub-tabs"""
    st.header("Loads and Mass Assignments")
    st.markdown("Define distributed loads on beams, node masses, and nodal loads.")
    
    if not st.session_state.model_created:
        st.warning("⚠️ Please create the model first.")
        return
    elif not st.session_state.elements_created:
        st.warning("⚠️ Please create structural elements first.")
        return
    
    # Show helpful message if model was loaded
    if st.session_state.get('editing_mode') and not st.session_state.loads_applied:
        st.info("ℹ️ **Model Loaded**: After loading a model, recreate the OpenSees model, confirm materials/sections, create elements, and then apply loads/masses here.")
    
    # Create sub-tabs for different load/mass types
    load_subtab1, load_subtab2, load_subtab3 = st.tabs([
        "📊 Distributed Loads on Beams",
        "⚖️ Node Masses",
        "📍 Nodal Loads"
    ])
    
    # ==================== SUB-TAB 1: DISTRIBUTED LOADS ====================
    with load_subtab1:
        st.subheader("Distributed Loads on Beams")
        st.markdown("Define uniform distributed loads on beams (kN/m).")
        
        # Load type selection
        load_type = st.radio(
            "Load Assignment Type:",
            options=['Same for All Floors', 'Floor-wise (Custom)'],
            help="Choose whether to use same loads for all floors or specify different loads per beam"
        )
        
        if load_type == 'Same for All Floors':
            col1, col2 = st.columns(2)
            
            # Get current values if loads were previously applied
            current_floor_load = st.session_state.get('floor_beam_loads', 70.0) if st.session_state.loads_applied else 70.0
            current_roof_load = st.session_state.get('roof_beam_loads', 50.0) if st.session_state.loads_applied else 50.0
            
            with col1:
                st.markdown("#### Typical Floor Beams")
                floor_beam_loads = st.number_input(
                    "Floor Load (kN/m)",
                    min_value=0.0,
                    max_value=500.0,
                    value=float(current_floor_load),
                    step=5.0,
                    help="Load on typical floor beams"
                )
            
            with col2:
                st.markdown("#### Roof Beams")
                roof_beam_loads = st.number_input(
                    "Roof Load (kN/m)",
                    min_value=0.0,
                    max_value=500.0,
                    value=float(current_roof_load),
                    step=5.0,
                    help="Load on roof beams"
                )
            
            st.markdown("---")
            
            # Show status and provide option to re-apply
            if st.session_state.loads_applied:
                st.success("✅ Loads have been applied previously. You can modify the values above and re-apply if needed.")
                col_apply, col_clear = st.columns(2)
                with col_apply:
                    if st.button("🔄 Re-apply Loads", type="primary", key="reapply_loads_button_2d"):
                        try:
                            with st.spinner("Applying loads..."):
                                ut.load_beams(
                                    -floor_beam_loads,
                                    -roof_beam_loads,
                                    st.session_state.tagbeams
                                )
                                
                                st.session_state.floor_beam_loads = floor_beam_loads
                                st.session_state.roof_beam_loads = roof_beam_loads
                                st.session_state.load_type = 'same'
                                st.session_state.loads_applied = True
                                
                                st.success("✅ Loads applied successfully!")
                                st.rerun()
                                
                        except Exception as e:
                            st.error(f"❌ Error applying loads: {str(e)}")
                with col_clear:
                    if st.button("🗑️ Clear Loads", type="secondary", key="clear_loads_button_2d"):
                        st.session_state.loads_applied = False
                        st.session_state.floor_beam_loads = 70.0
                        st.session_state.roof_beam_loads = 50.0
                        st.info("⚠️ Loads cleared. Model needs to be recreated and loads re-applied.")
                        st.rerun()
            else:
                if st.button("📊 Apply Loads", type="primary", key="apply_loads_button_2d"):
                    try:
                        with st.spinner("Applying loads..."):
                            ut.load_beams(
                                -floor_beam_loads,
                                -roof_beam_loads,
                                st.session_state.tagbeams
                            )
                            
                            st.session_state.floor_beam_loads = floor_beam_loads
                            st.session_state.roof_beam_loads = roof_beam_loads
                            st.session_state.load_type = 'same'
                            st.session_state.loads_applied = True
                            
                            st.success("✅ Loads applied successfully!")
                            st.rerun()
                            
                    except Exception as e:
                        st.error(f"❌ Error applying loads: {str(e)}")
        
        else:  # Floor-wise loads (actually beamwise - individual load per beam)
            st.markdown("#### Define loads for each beam (beamwise)")
            st.info("Specify individual loads for each beam. This allows different loads per beam, not just per floor.")
            
            n_floors = len(st.session_state.coordy) - 1
            n_spans = len(st.session_state.coordx) - 1
            
            # Initialize beam loads if not exists - store as {(floor, span): load_value}
            if 'beam_loads_beamwise' not in st.session_state:
                st.session_state.beam_loads_beamwise = {}
            
            # Create input for each beam - only for beams that exist
            for floor in range(1, n_floors + 1):
                is_roof = (floor == n_floors)
                default_load = 50.0 if is_roof else 70.0
                
                # Check which beams exist on this floor
                existing_beams = []
                for span_idx in range(n_spans):
                    if floor in st.session_state.beam_assignments:
                        if span_idx in st.session_state.beam_assignments[floor]:
                            if st.session_state.beam_assignments[floor][span_idx] != 'None':
                                existing_beams.append(span_idx)
                
                # Only show section if there are beams on this floor
                if existing_beams:
                    st.markdown(f"**Floor {floor} {'(Roof)' if is_roof else ''}:**")
                    cols = st.columns(len(existing_beams))
                    
                    for col_idx, span_idx in enumerate(existing_beams):
                        with cols[col_idx]:
                            beam_key = (floor, span_idx)
                            current_load = st.session_state.beam_loads_beamwise.get(beam_key, default_load)
                            
                            # Don't auto-update session state to avoid UI jumping
                            # Values will be read from widget state when Apply is clicked
                            st.number_input(
                                f"Span {span_idx+1}",
                                min_value=0.0,
                                max_value=500.0,
                                value=float(current_load),
                                step=5.0,
                                key=f"beam_load_f{floor}_s{span_idx}",
                                help=f"Load for beam at floor {floor}, span {span_idx+1}"
                            )
            
            st.markdown("---")
            
            # Show status and provide option to re-apply
            if st.session_state.loads_applied:
                st.success("✅ Loads have been applied previously. You can modify the values above and re-apply if needed.")
                col_apply2, col_clear2 = st.columns(2)
                with col_apply2:
                    if st.button("🔄 Re-apply Beamwise Loads", type="primary", key="reapply_loads_floorwise_2d"):
                        try:
                            with st.spinner("Applying loads..."):
                                # Read current values from widget state and save to session state
                                for floor in range(1, n_floors + 1):
                                    for span_idx in range(n_spans):
                                        if floor in st.session_state.beam_assignments:
                                            if span_idx in st.session_state.beam_assignments[floor]:
                                                if st.session_state.beam_assignments[floor][span_idx] != 'None':
                                                    widget_key = f"beam_load_f{floor}_s{span_idx}"
                                                    if widget_key in st.session_state:
                                                        beam_key = (floor, span_idx)
                                                        st.session_state.beam_loads_beamwise[beam_key] = st.session_state[widget_key]
                                
                                # Build nested load list for each floor
                                n_spans = len(st.session_state.coordx) - 1
                                beam_loads = []
                                
                                for floor in range(1, n_floors + 1):
                                    floor_loads = []
                                    for span in range(n_spans):
                                        if st.session_state.beam_assignments[floor][span] != 'None':
                                            beam_key = (floor, span)
                                            load_value = st.session_state.beam_loads_beamwise.get(beam_key, 70.0)
                                            floor_loads.append(-load_value)
                                    beam_loads.append(floor_loads)
                                
                                st.session_state.beam_loads = beam_loads
                                ut.load_beams2(beam_loads, st.session_state.tagbeams, output=1)
                                
                                st.session_state.load_type = 'beamwise'
                                st.session_state.loads_applied = True
                                
                                st.success("✅ Beamwise loads applied successfully!")
                                st.rerun()
                                
                        except Exception as e:
                            st.error(f"❌ Error applying loads: {str(e)}")
                            import traceback
                            st.code(traceback.format_exc())
                with col_clear2:
                    if st.button("🗑️ Clear Loads", type="secondary", key="clear_loads_floorwise_2d"):
                        st.session_state.loads_applied = False
                        st.session_state.beam_loads_beamwise = {}
                        st.info("⚠️ Loads cleared. Model needs to be recreated and loads re-applied.")
                        st.rerun()
            else:
                if st.button("📊 Apply Floor-wise Loads", type="primary", key="apply_loads_floorwise_2d"):
                    try:
                        with st.spinner("Applying loads..."):
                            # Read current values from widget state and save to session state
                            for floor in range(1, n_floors + 1):
                                for span_idx in range(n_spans):
                                    if floor in st.session_state.beam_assignments:
                                        if span_idx in st.session_state.beam_assignments[floor]:
                                            if st.session_state.beam_assignments[floor][span_idx] != 'None':
                                                widget_key = f"beam_load_f{floor}_s{span_idx}"
                                                if widget_key in st.session_state:
                                                    beam_key = (floor, span_idx)
                                                    st.session_state.beam_loads_beamwise[beam_key] = st.session_state[widget_key]
                            
                            # Build nested load list for each floor
                            n_spans = len(st.session_state.coordx) - 1
                            beam_loads = []
                            
                            for floor in range(1, n_floors + 1):
                                floor_loads = []
                                for span in range(n_spans):
                                    if st.session_state.beam_assignments[floor][span] != 'None':
                                        beam_key = (floor, span)
                                        load_value = st.session_state.beam_loads_beamwise.get(beam_key, 70.0)
                                        floor_loads.append(-load_value)
                                beam_loads.append(floor_loads)
                            
                            st.session_state.beam_loads = beam_loads
                            ut.load_beams2(beam_loads, st.session_state.tagbeams, output=1)
                            
                            st.session_state.load_type = 'beamwise'
                            st.session_state.loads_applied = True
                            
                            st.success("✅ Beamwise loads applied successfully!")
                            st.rerun()
                            
                    except Exception as e:
                        st.error(f"❌ Error applying loads: {str(e)}")
                        import traceback
                        st.code(traceback.format_exc())
    
    # ==================== SUB-TAB 2: NODE MASSES ====================
    with load_subtab2:
        st.subheader("Node Masses")
        st.markdown("Assign masses to nodes for dynamic analysis. Mass is applied in X and Y directions (ton).")
        
        # Get updated node information
        try:
            nodes_tags_updated = getNodeTags()
            coordx_updated = np.array([nodeCoord(i)[0] for i in nodes_tags_updated])
            coordy_updated = np.array([nodeCoord(i)[1] for i in nodes_tags_updated])
            node_info_updated = np.column_stack((np.array(nodes_tags_updated), coordx_updated, coordy_updated))
        except:
            st.error("❌ Could not retrieve node information. Please ensure elements have been created.")
            return
        
        # Batch assignment option
        st.markdown("#### Batch Mass Assignment")
        col_batch1, col_batch2 = st.columns([2, 1])
        with col_batch1:
            batch_mass_value = st.number_input(
                "Mass value to assign (ton)",
                min_value=0.0,
                max_value=1000.0,
                value=10.0,
                step=1.0,
                help="Single mass value to apply to multiple nodes"
            )
        with col_batch2:
            if st.button("📝 Apply to All Nodes", key="batch_mass_all"):
                for node_tag in nodes_tags_updated:
                    st.session_state.node_masses[int(node_tag)] = batch_mass_value
                st.success(f"✅ Applied {batch_mass_value} ton to all {len(nodes_tags_updated)} nodes")
                st.rerun()
        
        st.markdown("---")
        st.markdown("#### Individual Node Mass Assignment")
        st.info("Edit masses for individual nodes. Changes are saved automatically.")
        
        # Create dataframe for editing
        mass_data = []
        for node_tag, x, y in node_info_updated:
            current_mass = st.session_state.node_masses.get(int(node_tag), 0.0)
            mass_data.append({
                'Node': int(node_tag),
                'X (m)': f"{x:.3f}",
                'Y (m)': f"{y:.3f}",
                'Mass (ton)': current_mass
            })
        
        mass_df = pd.DataFrame(mass_data)
        
        # Use data editor for table
        edited_mass_df = st.data_editor(
            mass_df,
            column_config={
                "Node": st.column_config.NumberColumn("Node", disabled=True),
                "X (m)": st.column_config.TextColumn("X (m)", disabled=True),
                "Y (m)": st.column_config.TextColumn("Y (m)", disabled=True),
                "Mass (ton)": st.column_config.NumberColumn(
                    "Mass (ton)",
                    min_value=0.0,
                    max_value=1000.0,
                    step=0.1,
                    format="%.2f"
                ),
            },
            hide_index=True,
            use_container_width=True,
            key="mass_editor"
        )
        
        # Update session state with edited values
        for idx, row in edited_mass_df.iterrows():
            node_tag = int(row['Node'])
            mass_value = row['Mass (ton)']
            st.session_state.node_masses[node_tag] = mass_value
        
        st.markdown("---")
        
        # Apply masses button
        if st.session_state.masses_assigned:
            st.success("✅ Masses have been applied previously.")
            col_m1, col_m2 = st.columns(2)
            with col_m1:
                if st.button("🔄 Re-apply Masses", type="primary", key="reapply_masses"):
                    try:
                        with st.spinner("Re-applying masses..."):
                            count = 0
                            for node_tag, mass_val in st.session_state.node_masses.items():
                                if mass_val > 0:
                                    mass(int(node_tag), mass_val, mass_val, 0.0)
                                    count += 1
                            st.session_state.masses_assigned = True
                        st.success(f"✅ Successfully re-applied masses to {count} nodes!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error applying masses: {str(e)}")
            with col_m2:
                if st.button("🗑️ Clear Masses", type="secondary", key="clear_masses"):
                    st.session_state.masses_assigned = False
                    st.session_state.node_masses = {}
                    st.info("⚠️ Masses cleared from session state.")
                    st.rerun()
        else:
            if st.button("⚖️ Apply Masses", type="primary", key="apply_masses"):
                try:
                    with st.spinner("Applying masses..."):
                        count = 0
                        for node_tag, mass_val in st.session_state.node_masses.items():
                            if mass_val > 0:
                                mass(int(node_tag), mass_val, mass_val, 0.0)
                                count += 1
                        st.session_state.masses_assigned = True
                    st.success(f"✅ Successfully applied masses to {count} nodes!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error applying masses: {str(e)}")
    
    # ==================== SUB-TAB 3: NODAL LOADS ====================
    with load_subtab3:
        st.subheader("Nodal Loads")
        st.markdown("Assign concentrated loads at nodes: Fx (kN), Fy (kN), Mz (kN-m).")
        
        # Get node information
        try:
            nodes_tags_updated = getNodeTags()
            coordx_updated = np.array([nodeCoord(i)[0] for i in nodes_tags_updated])
            coordy_updated = np.array([nodeCoord(i)[1] for i in nodes_tags_updated])
            node_info_updated = np.column_stack((np.array(nodes_tags_updated), coordx_updated, coordy_updated))
        except:
            st.error("❌ Could not retrieve node information. Please ensure elements have been created.")
            return
        
        # Batch assignment option
        st.markdown("#### Batch Nodal Load Assignment")
        col_b1, col_b2, col_b3, col_b4 = st.columns([1, 1, 1, 1])
        with col_b1:
            batch_fx = st.number_input("Fx (kN)", value=0.0, step=1.0, key="batch_fx")
        with col_b2:
            batch_fy = st.number_input("Fy (kN)", value=0.0, step=1.0, key="batch_fy")
        with col_b3:
            batch_mz = st.number_input("Mz (kN-m)", value=0.0, step=1.0, key="batch_mz")
        with col_b4:
            st.markdown("<br>", unsafe_allow_html=True)  # spacer
            if st.button("📝 Apply to All", key="batch_load_all"):
                for node_tag in nodes_tags_updated:
                    st.session_state.node_loads[int(node_tag)] = {
                        'Fx': batch_fx,
                        'Fy': batch_fy,
                        'Mz': batch_mz
                    }
                st.success(f"✅ Applied loads to all {len(nodes_tags_updated)} nodes")
                st.rerun()
        
        st.markdown("---")
        st.markdown("#### Individual Nodal Load Assignment")
        st.info("Edit loads for individual nodes (Fx, Fy, Mz). Changes are saved automatically.")
        
        # Create dataframe for editing
        load_data = []
        for node_tag, x, y in node_info_updated:
            current_load = st.session_state.node_loads.get(int(node_tag), {'Fx': 0.0, 'Fy': 0.0, 'Mz': 0.0})
            load_data.append({
                'Node': int(node_tag),
                'X (m)': f"{x:.3f}",
                'Y (m)': f"{y:.3f}",
                'Fx (kN)': current_load['Fx'],
                'Fy (kN)': current_load['Fy'],
                'Mz (kN-m)': current_load['Mz']
            })
        
        load_df = pd.DataFrame(load_data)
        
        # Use data editor for table
        edited_load_df = st.data_editor(
            load_df,
            column_config={
                "Node": st.column_config.NumberColumn("Node", disabled=True),
                "X (m)": st.column_config.TextColumn("X (m)", disabled=True),
                "Y (m)": st.column_config.TextColumn("Y (m)", disabled=True),
                "Fx (kN)": st.column_config.NumberColumn("Fx (kN)", step=1.0, format="%.2f"),
                "Fy (kN)": st.column_config.NumberColumn("Fy (kN)", step=1.0, format="%.2f"),
                "Mz (kN-m)": st.column_config.NumberColumn("Mz (kN-m)", step=1.0, format="%.2f"),
            },
            hide_index=True,
            use_container_width=True,
            key="load_editor"
        )
        
        # Update session state with edited values
        for idx, row in edited_load_df.iterrows():
            node_tag = int(row['Node'])
            st.session_state.node_loads[node_tag] = {
                'Fx': row['Fx (kN)'],
                'Fy': row['Fy (kN)'],
                'Mz': row['Mz (kN-m)']
            }
        
        st.markdown("---")
        
        # Apply nodal loads button
        if st.session_state.nodal_loads_assigned:
            st.success("✅ Nodal loads have been applied previously.")
            col_l1, col_l2 = st.columns(2)
            with col_l1:
                if st.button("🔄 Re-apply Nodal Loads", type="primary", key="reapply_nodal_loads"):
                    try:
                        with st.spinner("Re-applying nodal loads..."):
                            count = 0
                            for node_tag, loads in st.session_state.node_loads.items():
                                if loads['Fx'] != 0 or loads['Fy'] != 0 or loads['Mz'] != 0:
                                    load(int(node_tag), loads['Fx'], loads['Fy'], loads['Mz'])
                                    count += 1
                            st.session_state.nodal_loads_assigned = True
                        st.success(f"✅ Successfully re-applied nodal loads to {count} nodes!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error applying nodal loads: {str(e)}")
            with col_l2:
                if st.button("🗑️ Clear Nodal Loads", type="secondary", key="clear_nodal_loads"):
                    st.session_state.nodal_loads_assigned = False
                    st.session_state.node_loads = {}
                    st.info("⚠️ Nodal loads cleared from session state.")
                    st.rerun()
        else:
            if st.button("📍 Apply Nodal Loads", type="primary", key="apply_nodal_loads"):
                try:
                    with st.spinner("Applying nodal loads..."):
                        count = 0
                        for node_tag, loads in st.session_state.node_loads.items():
                            if loads['Fx'] != 0 or loads['Fy'] != 0 or loads['Mz'] != 0:
                                load(int(node_tag), loads['Fx'], loads['Fy'], loads['Mz'])
                                count += 1
                        st.session_state.nodal_loads_assigned = True
                    st.success(f"✅ Successfully applied nodal loads to {count} nodes!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error applying nodal loads: {str(e)}")


# ==================== TAB 7: SAVE MODEL ====================
def render_save_model_tab():
    """Render Save Model tab for 2D model"""
    st.header("Save Model")
    st.markdown("Save the complete 2D model configuration to a file for later use.")
    
    if not st.session_state.model_created:
        st.warning("⚠️ Please create a model first.")
        return
    
    if not st.session_state.materials:
        st.warning("⚠️ Please define at least one material.")
        return
    
    if not st.session_state.sections:
        st.warning("⚠️ Please define at least one section.")
        return
    
    # Check assignments
    num_floors = len(st.session_state.coordy) - 1
    all_columns_configured = all(f in st.session_state.column_assignments for f in range(1, num_floors + 1))
    all_beams_configured = all(f in st.session_state.beam_assignments for f in range(1, num_floors + 1))
    
    if not (all_columns_configured and all_beams_configured):
        st.warning("⚠️ Please complete all column and beam assignments before saving.")
        return
    
    st.success("✅ Model is ready to be saved!")
    
    st.markdown("---")
    st.subheader("Save Configuration")
    
    # Prepare model data
    model_data = {
        'project_name': st.session_state.project_name,
        'coordx': st.session_state.coordx,
        'coordy': st.session_state.coordy,
        'materials': st.session_state.materials,
        'sections': st.session_state.sections,
        'column_assignments': st.session_state.column_assignments,
        'beam_assignments': st.session_state.beam_assignments,
        'model_created': st.session_state.model_created,
        'elements_created': st.session_state.elements_created,
        'loads_applied': st.session_state.loads_applied,
        'masses_assigned': st.session_state.get('masses_assigned', False),
        'nodal_loads_assigned': st.session_state.get('nodal_loads_assigned', False),
        'node_masses': st.session_state.get('node_masses', {}),
        'node_loads': st.session_state.get('node_loads', {}),
        # Infill data
        'masonry_materials': st.session_state.get('masonry_materials', {}),
        'infill_assignments': st.session_state.get('infill_assignments', {}),
        'width_percentage': st.session_state.get('width_percentage', 0.25),
        'infills_assigned': st.session_state.get('infills_assigned', False),
    }

    # Add optional data if exists
    if st.session_state.loads_applied:
        model_data['load_type'] = st.session_state.get('load_type', 'same')
        if model_data['load_type'] == 'same':
            model_data['floor_beam_loads'] = st.session_state.get('floor_beam_loads')
            model_data['roof_beam_loads'] = st.session_state.get('roof_beam_loads')
        else:
            model_data['beam_loads_beamwise'] = st.session_state.get('beam_loads_beamwise', {})
    
    # Show editing status
    if st.session_state.editing_mode:
        st.info(f"🔧 **Editing Mode**: Original model from '{st.session_state.loaded_model_name}'")
        
        col_save1, col_save2 = st.columns(2)
        
        with col_save1:
            st.markdown("**Option 1: Overwrite Original**")
            original_name = os.path.basename(st.session_state.loaded_model_name).replace('.pkl', '')
            st.text_input(
                "Original filename:",
                value=original_name,
                disabled=True,
                key="original_name_display_2d"
            )
            
            overwrite_confirm = st.checkbox(
                "I confirm I want to overwrite the original model",
                key="overwrite_confirm_2d"
            )
            
            if st.button("💾 Overwrite Original", type="secondary", key="overwrite_button_2d", disabled=not overwrite_confirm):
                try:
                    file_path = f"models/{original_name}.pkl"
                    os.makedirs("models", exist_ok=True)
                    with open(file_path, 'wb') as f:
                        pickle.dump(model_data, f)
                    st.success(f"✅ Model overwritten successfully: {file_path}")
                    st.info("💡 You can load this model later using the 'Load/New Model' tab.")
                    st.session_state.model_modified = False
                except Exception as e:
                    st.error(f"❌ Error saving model: {str(e)}")
        
        with col_save2:
            st.markdown("**Option 2: Save As New**")
            new_name = st.text_input(
                "New filename (without extension):",
                value=f"{st.session_state.project_name}_edited",
                help="Enter a new name to save as a copy",
                key="new_name_2d"
            )
            
            if st.button("💾 Save As New Model", type="primary", key="save_as_button_2d"):
                if new_name == original_name:
                    st.error("⚠️ New name cannot be the same as original. Use 'Overwrite' option instead.")
                elif new_name == "":
                    st.error("⚠️ Please enter a filename.")
                else:
                    try:
                        file_path = f"models/{new_name}.pkl"
                        os.makedirs("models", exist_ok=True)
                        model_data['project_name'] = new_name
                        with open(file_path, 'wb') as f:
                            pickle.dump(model_data, f)
                        st.success(f"✅ Model saved as new file: {file_path}")
                        st.info("💡 Original model preserved. You can load either model later.")
                        # Update session state to reflect new model
                        st.session_state.loaded_model_name = file_path
                        st.session_state.project_name = new_name
                    except Exception as e:
                        st.error(f"❌ Error saving model: {str(e)}")
    else:
        # New model mode - simple save
        st.info("🆕 **New Model Mode**: Saving for the first time")
        
        project_name = st.text_input(
            "Filename (without extension):",
            value=st.session_state.project_name,
            help="Name for the saved model file",
            key="project_name_save_2d"
        )
        
        if st.button("💾 Save Model", type="primary", key="save_model_button_2d"):
            try:
                file_path = f"models/{project_name}.pkl"
                os.makedirs("models", exist_ok=True)
                model_data['project_name'] = project_name
                with open(file_path, 'wb') as f:
                    pickle.dump(model_data, f)
                st.success(f"✅ Model saved successfully to: {file_path}")
                st.info("💡 You can now load this model later using the 'Load/New Model' tab.")
                # Update session state
                st.session_state.loaded_model_name = file_path
                st.session_state.editing_mode = True
                st.session_state.project_name = project_name
            except Exception as e:
                st.error(f"❌ Error saving model: {str(e)}")


# ==================== DEBUG SCRIPT GENERATION ====================
def generate_debug_script_from_state(session_state, n_floors, n_x_positions, n_spans):
    """Generate a Python script matching the current app configuration"""
    
    script = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Debug Script - Generated from App Configuration
Compare this with master_script_infills_pushover_with_masses_and_nodal_loads.py
"""

from openseespy.opensees import *
import matplotlib.pyplot as plt
import opseestools.analisis as an
import opseestools.utilidades as ut
import opsvis as opsv
import numpy as np
import itertools

#%% Model Setup
wipe()
model('basic','-ndm',2,'-ndf',3)

#%% Coordinates
'''
    
    # Add coordinates
    script += f"coordx = {session_state.coordx}\n"
    script += f"coordy = {session_state.coordy}\n"
    script += "ut.creategrid(coordx,coordy)\n"
    script += "fixY(0,1,1,1)\n\n"

    # Diagonal pairs for infill modeling
    script += "#%% Diagonal Pairs for Infills\n"
    script += "diagonal_pairs, diagonal_lengths = ut.get_diagonal_node_pairs(coordx, coordy)\n\n"

    # Add materials - store variable names for later use
    material_var_map = {}  # Maps material name to variable names dict
    script += "#%% Materials\n"
    for mat_idx, (mat_name, mat_props) in enumerate(session_state.materials.items()):
        var_suffix = f"_{mat_idx+1}" if mat_idx > 0 else ""
        script += f"# Material: {mat_name}\n"
        script += f"fc{var_suffix} = {mat_props['fc']}  # MPa\n"
        script += f"fy{var_suffix} = {mat_props['fy']}  # MPa\n"
        script += f"tag_noconf{var_suffix}, tag_conf{var_suffix}, tag_acero{var_suffix} = ut.col_materials(fc{var_suffix}, fy{var_suffix}, '{mat_props['detailing']}', nps=3)\n\n"
        
        # Store variable names for this material
        material_var_map[mat_name] = {
            'noconf': f"tag_noconf{var_suffix}",
            'conf': f"tag_conf{var_suffix}",
            'acero': f"tag_acero{var_suffix}"
        }
        
        # If first material, also create non-suffixed variables for backward compatibility
        if mat_idx == 0:
            material_var_map[mat_name]['noconf'] = 'tag_noconf'
            material_var_map[mat_name]['conf'] = 'tag_conf'
            material_var_map[mat_name]['acero'] = 'tag_acero'
    
    # Add masonry materials
    mas_var_map = {}  # Maps masonry material name to tag variable name
    if session_state.get('masonry_materials'):
        script += "#%% Masonry Materials\n"
        for mas_idx, (mas_name, mas_props) in enumerate(session_state.masonry_materials.items()):
            var_name = f"tag_mas" if mas_idx == 0 else f"tag_mas_{mas_idx+1}"
            script += f"# Masonry Material: {mas_name}\n"
            script += f"{var_name} = {mas_props['tag']}\n"
            script += f"ut.col_infill({mas_props['fm']}, {var_name}, brick_type='{mas_props['brick_type']}')\n\n"
            mas_var_map[mas_name] = var_name

    # Add rebar areas
    script += "#%% Rebar Areas\n"
    for rebar_name, rebar_area in REBAR_AREAS.items():
        script += f"{rebar_name} = {rebar_area}\n"
    script += "\n"
    
    # Add sections with variable names
    script += "#%% Sections\n"
    script += "c = 0.05  # Default concrete cover (m)\n\n"
    
    for sec_name, sec_props in session_state.sections.items():
        mat_name = sec_props['material']
        mat_vars = material_var_map[mat_name]
        
        script += f"# Section: {sec_name}\n"
        script += f"B{sec_name} = {sec_props['B']}\n"
        script += f"H{sec_name} = {sec_props['H']}\n"
        script += f"{sec_name}_tag = {sec_props['tag']}\n"
        
        # Check if has middle bars
        if sec_props['bars_middle'] == 0:
            script += f"ut.create_rect_RC_section({sec_name}_tag, H{sec_name}, B{sec_name}, c, "
            script += f"{mat_vars['conf']}, {mat_vars['noconf']}, {mat_vars['acero']}, "
            script += f"{sec_props['bars_top']}, {sec_props['area_top']}, "
            script += f"{sec_props['bars_bottom']}, {sec_props['area_bottom']})\n"
        else:
            script += f"ut.create_rect_RC_section({sec_name}_tag, H{sec_name}, B{sec_name}, c, "
            script += f"{mat_vars['conf']}, {mat_vars['noconf']}, {mat_vars['acero']}, "
            script += f"{sec_props['bars_top']}, {sec_props['area_top']}, "
            script += f"{sec_props['bars_bottom']}, {sec_props['area_bottom']}, "
            script += f"{sec_props['bars_middle']}, {sec_props['area_middle']})\n"
    script += "\n"
    
    # Add building elements using section variable names
    script += "#%% Elements\n"
    script += "building_columns = [\n"
    for floor in range(1, n_floors + 1):
        floor_cols = []
        for x_idx in range(n_x_positions):
            section_name = session_state.column_assignments.get(floor, {}).get(x_idx, 'None')
            if section_name == 'None' or section_name is None:
                floor_cols.append("'None'")
            else:
                floor_cols.append(f"{section_name}_tag")
        script += f"    [{', '.join(floor_cols)}],  # Floor {floor}\n"
    script += "]\n\n"
    
    script += "building_beams = [\n"
    for floor in range(1, n_floors + 1):
        floor_beams = []
        for span_idx in range(n_spans):
            section_name = session_state.beam_assignments.get(floor, {}).get(span_idx, 'None')
            if section_name == 'None' or section_name is None:
                floor_beams.append("'None'")
            else:
                floor_beams.append(f"{section_name}_tag")
        script += f"    [{', '.join(floor_beams)}],  # Floor {floor}\n"
    script += "]\n\n"
    
    script += "tagcols, tagbeams, column_info, beam_info = ut.create_elements2(coordx, coordy, building_columns, building_beams, output=1)\n"
    script += "ut.remove_hanging_nodes(tagcols, tagbeams)\n\n"
    
    # Add diaphragms
    if 'floor_diaphragms' in session_state:
        script += "#%% Diaphragms\n"
        script += f"floor_diaphragms = {session_state.floor_diaphragms}\n"
        script += "ut.apply_diaphragms(floor_diaphragms, output=1)\n\n"
    
    # Add infill assignments
    if session_state.get('infills_assigned', False) and session_state.get('infill_assignments'):
        script += "#%% Masonry Thickness and Widths\n"
        script += "negligible_thickness = 1e-10\n"
        script += f"width_percentage = {session_state.get('width_percentage', 0.25)}\n\n"

        # Determine valid panels
        valid_panels = get_valid_panels(
            session_state.coordx,
            session_state.coordy,
            session_state.model_node_tags
        ) if session_state.get('model_node_tags') else {}

        # Build thickness list
        script += "building_infill_thickness = [\n"
        for f in range(1, n_floors + 1):
            floor_thicknesses = []
            for s in range(n_spans):
                is_valid = valid_panels.get(f, {}).get(s, False)
                assignment = session_state.infill_assignments.get(f, {}).get(s, {})
                mat_name = assignment.get('material_name', 'None')
                if is_valid and mat_name != 'None':
                    floor_thicknesses.append(str(assignment.get('thickness', 0.1)))
                else:
                    floor_thicknesses.append("negligible_thickness")
            script += f"    [{', '.join(floor_thicknesses)}],  # Floor {f}\n"
        script += "]\n\n"

        script += "building_infill_widths = ut.infill_widths(diagonal_lengths, width_percentage)\n"
        script += "building_infill_areas = (np.array(building_infill_thickness) * np.array(building_infill_widths)).tolist()\n\n"

        # Build materials list
        script += "#%% Masonry Material Assignments\n"
        script += "building_infill_materials = [\n"
        for f in range(1, n_floors + 1):
            floor_mats = []
            for s in range(n_spans):
                is_valid = valid_panels.get(f, {}).get(s, False)
                assignment = session_state.infill_assignments.get(f, {}).get(s, {})
                mat_name = assignment.get('material_name', 'None')
                if is_valid and mat_name != 'None' and mat_name in mas_var_map:
                    floor_mats.append(mas_var_map[mat_name])
                else:
                    floor_mats.append("'None'")
            script += f"    [{', '.join(floor_mats)}],  # Floor {f}\n"
        script += "]\n\n"

        script += "ut.assign_infills(diagonal_pairs, building_infill_areas, building_infill_materials)\n\n"

    # Add distributed loads on beams
    if session_state.loads_applied:
        script += "#%% Distributed Loads on Beams\n"
        if session_state.get('load_type') == 'same':
            script += f"floor_beam_loads = {session_state.get('floor_beam_loads')}\n"
            script += f"roof_beam_loads = {session_state.get('roof_beam_loads')}\n"
            script += "ut.load_beams(-floor_beam_loads, -roof_beam_loads, tagbeams)\n\n"
        else:
            if 'beam_loads' in session_state:
                script += f"beam_loads = {session_state.beam_loads}\n"
                script += "ut.load_beams2(beam_loads, tagbeams, output=1)\n\n"
    
    # Add node masses
    if session_state.get('masses_assigned', False) and session_state.get('node_masses', {}):
        script += "#%% Node Masses\n"
        script += "# Get updated node information\n"
        script += "nodes_tags_updated = getNodeTags()\n"
        script += "coordx_updated = np.array([nodeCoord(i)[0] for i in nodes_tags_updated])\n"
        script += "coordy_updated = np.array([nodeCoord(i)[1] for i in nodes_tags_updated])\n"
        script += "node_info_updated = np.column_stack((np.array(nodes_tags_updated), coordx_updated, coordy_updated))\n\n"
        script += "# Assign masses to nodes (ton)\n"
        for node_tag, mass_val in session_state.node_masses.items():
            if mass_val > 0:
                script += f"mass({node_tag}, {mass_val}, {mass_val}, 0.0)\n"
        script += "\n"
    
    # Add nodal loads
    if session_state.get('nodal_loads_assigned', False) and session_state.get('node_loads', {}):
        script += "#%% Nodal Loads\n"
        script += "# Assign concentrated loads at nodes: Fx (kN), Fy (kN), Mz (kN-m)\n"
        for node_tag, loads in session_state.node_loads.items():
            if loads['Fx'] != 0 or loads['Fy'] != 0 or loads['Mz'] != 0:
                script += f"load({node_tag}, {loads['Fx']}, {loads['Fy']}, {loads['Mz']})\n"
        script += "\n"
    
    # Add analysis
    script += "#%% Gravity Analysis\n"
    script += "an.gravedad()\n"
    script += "loadConst('-time', 0.0)\n\n"
    
    script += "#%% Pushover Analysis\n"
    script += "leftmost_nodes = ut.find_leftmost_nodes(coordy)\n"
    script += "ut.pushover_loads(coordy, nodes=leftmost_nodes)\n"
    script += "elements = tagcols + tagbeams\n"
    script += "nodes_control = [1000] + [int(i) for i in leftmost_nodes]\n"
    script += "control_node = getNodeTags()[-1]\n"
    script += "target_disp = 0.05 * coordy[-1]  # 5% drift\n"
    script += "increment = 0.001\n\n"
    script += "print(f'Control node: {control_node}')\n"
    script += "print(f'Leftmost nodes: {leftmost_nodes}')\n"
    script += "print(f'Nodes control: {nodes_control}')\n"
    script += "print(f'Elements count: {len(elements)}')\n\n"
    script += "dtecho, Vbasal, drifts, rotations = an.pushover2DRot(target_disp, increment, control_node, 1, nodes_control, elements)\n\n"
    
    script += "#%% Results\n"
    script += "print(f'Analysis completed: {len(dtecho)} steps')\n"
    script += "print(f'Max base shear: {max(Vbasal):.2f} kN')\n"
    script += "print(f'Max roof displacement: {max(dtecho):.4f} m')\n\n"
    
    script += "#%% Plot - EXACT SAME AS MASTER SCRIPT\n"
    script += "plt.figure(figsize=(10, 6))\n"
    script += "plt.plot(drifts[:len(Vbasal), 0], Vbasal)\n"
    script += "plt.xlabel('First Floor Drift')\n"
    script += "plt.ylabel('Base Shear (kN)')\n"
    script += "plt.title('Capacity Curve - First Floor Drift vs Base Shear')\n"
    script += "plt.grid(True)\n"
    script += "plt.show()\n"
    
    return script


# ==================== TAB 9: MODAL ANALYSIS ====================
def render_modal_analysis_tab():
    """Render Modal Analysis tab"""
    st.header("Modal Analysis")
    st.markdown("Compute modal properties of the structure (natural frequencies, periods, mode shapes).")
    
    if not st.session_state.model_created:
        st.warning("⚠️ Please create the model first.")
        return
    elif not st.session_state.elements_created:
        st.warning("⚠️ Please create structural elements first.")
        return
    elif not st.session_state.get('masses_assigned', False):
        st.warning("⚠️ Please assign node masses first (Tab 6: Loads and Mass Assignments → Node Masses).")
        st.info("💡 Modal analysis requires masses to be defined at the nodes.")
        return
    
    st.markdown("---")
    st.subheader("📊 Run Modal Analysis")
    
    st.info("""
    **Modal Properties Command**: This will compute eigenvalues and eigenvectors of the structure.
    
    The results include:
    - Natural frequencies (rad/s and Hz)
    - Periods (seconds)
    - Mode shapes (eigenvectors)
    - Modal participation factors
    
    Results will be printed to the output below.
    """)
    
    # Button to run modal analysis
    if st.button("🔬 Compute Modal Properties", type="primary", key="run_modal_analysis"):
        try:
            with st.spinner("Computing modal properties..."):
                # First compute eigenvalues - need to call eigen before modalProperties
                # Number of modes = 2 * number of floors (2 DOF per floor for 2D frame)
                n_modes = 2 * (len(st.session_state.coordy) - 1)
                eigen(n_modes)
                
                # Run modal analysis - write to file
                modal_report_file = 'ModalReport.txt'
                modalProperties('-print', '-file', modal_report_file, '-unorm')
                
                # Read the output file
                if os.path.exists(modal_report_file):
                    with open(modal_report_file, 'r') as f:
                        modal_output = f.read()
                    
                    # Store in session state
                    st.session_state.modal_analysis_output = modal_output
                    st.session_state.modal_analysis_done = True
                    
                    st.success("✅ Modal analysis completed successfully!")
                    st.rerun()
                else:
                    st.error("❌ Modal report file was not created.")
                    st.session_state.modal_analysis_done = False
                
        except Exception as e:
            st.error(f"❌ Error in modal analysis: {str(e)}")
            import traceback
            st.code(traceback.format_exc())
    
    # Display results if available
    if st.session_state.get('modal_analysis_done', False) and 'modal_analysis_output' in st.session_state:
        st.markdown("---")
        st.subheader("📄 Modal Analysis Results")
        
        modal_output = st.session_state.modal_analysis_output
        
        if modal_output.strip():
            # Display the output in a code block
            st.code(modal_output, language='text')
            
            # Provide download option
            st.download_button(
                label="💾 Download Modal Analysis Results",
                data=modal_output,
                file_name="modal_analysis_results.txt",
                mime="text/plain",
                key="download_modal_results"
            )
        else:
            st.warning("⚠️ Modal analysis completed but no output was generated.")
            st.info("This might happen if the model doesn't have enough degrees of freedom or if masses are not properly defined.")


# ==================== TAB 10: ANALYSIS ====================
def render_analysis_tab():
    """Render Analysis tab for gravity and pushover analysis"""
    st.header("Structural Analysis")
    st.markdown("Perform gravity analysis and pushover analysis on the 2D frame.")
    
    if not st.session_state.model_created:
        st.warning("⚠️ Please create the model first.")
        return
    elif not st.session_state.elements_created:
        st.warning("⚠️ Please create structural elements first.")
        return
    elif not st.session_state.loads_applied:
        st.warning("⚠️ Please apply loads first.")
        return
    
    # Analysis section
    st.subheader("🔬 Analysis Options")
    
    # Debugging Section
    with st.expander("🐛 Debug Information - Model Configuration", expanded=False):
        st.markdown("### Model Setup Details")
        
        st.markdown("#### 1. Coordinates")
        st.write(f"**coordx:** {st.session_state.coordx}")
        st.write(f"**coordy:** {st.session_state.coordy}")
        st.write(f"**n_floors:** {len(st.session_state.coordy) - 1}")
        
        st.markdown("#### 2. Building Elements Structure")
        n_floors = len(st.session_state.coordy) - 1
        n_x_positions = len(st.session_state.coordx)
        n_spans = len(st.session_state.coordx) - 1
        
        # Show building_columns
        st.markdown("**building_columns (by floor):**")
        building_columns_debug = []
        for floor in range(1, n_floors + 1):
            floor_cols = []
            for x_idx in range(n_x_positions):
                section_name = st.session_state.column_assignments.get(floor, {}).get(x_idx, 'None')
                if section_name == 'None' or section_name is None:
                    floor_cols.append('None')
                else:
                    tag = st.session_state.sections[section_name]['tag']
                    floor_cols.append(f"{section_name}(tag:{tag})")
            building_columns_debug.append(floor_cols)
            st.write(f"Floor {floor}: {floor_cols}")
        
        # Show building_beams
        st.markdown("**building_beams (by floor):**")
        building_beams_debug = []
        for floor in range(1, n_floors + 1):
            floor_beams = []
            for span_idx in range(n_spans):
                section_name = st.session_state.beam_assignments.get(floor, {}).get(span_idx, 'None')
                if section_name == 'None' or section_name is None:
                    floor_beams.append('None')
                else:
                    tag = st.session_state.sections[section_name]['tag']
                    floor_beams.append(f"{section_name}(tag:{tag})")
            building_beams_debug.append(floor_beams)
            st.write(f"Floor {floor}: {floor_beams}")
        
        st.markdown("#### 3. Element Tags")
        if st.session_state.elements_created:
            st.write(f"**tagcols (first 10):** {st.session_state.tagcols[:10]}...")
            st.write(f"**tagcols length:** {len(st.session_state.tagcols)}")
            st.write(f"**tagbeams (first 10):** {st.session_state.tagbeams[:10]}...")
            st.write(f"**tagbeams length:** {len(st.session_state.tagbeams)}")
        else:
            st.write("Elements not created yet")
        
        st.markdown("#### 4. Diaphragm Configuration")
        if 'floor_diaphragms' in st.session_state:
            st.write(f"**floor_diaphragms:** {st.session_state.floor_diaphragms}")
            diaphragm_floors = [f+1 for f, val in enumerate(st.session_state.floor_diaphragms) if val == 1]
            st.write(f"**Floors with diaphragms:** {diaphragm_floors}")
        
        st.markdown("#### 5. Load Configuration")
        if st.session_state.loads_applied:
            if st.session_state.get('load_type') == 'same':
                st.write(f"**Load Type:** Same for all floors")
                st.write(f"**Floor beam loads:** {st.session_state.get('floor_beam_loads')} kN/m")
                st.write(f"**Roof beam loads:** {st.session_state.get('roof_beam_loads')} kN/m")
            else:
                st.write(f"**Load Type:** Beamwise (individual per beam)")
                if 'beam_loads' in st.session_state:
                    st.write(f"**beam_loads (nested list):** {st.session_state.beam_loads}")
                elif 'beam_loads_beamwise' in st.session_state:
                    for (floor, span), load in st.session_state.beam_loads_beamwise.items():
                        st.write(f"  Floor {floor}, Span {span+1}: {load} kN/m")
        else:
            st.write("Loads not applied yet")
    
    st.markdown("---")


# ==================== TAB 9: PUSHOVER RESULTS ====================
def render_pushover_results_tab():
    """Render Pushover Results tab with load functionality and interactive plots"""
    st.header("Pushover Analysis Results")
    st.markdown("Load and visualize pushover analysis results with interactive plots.")
    
    # Load results section
    st.subheader("📂 Load Pushover Results")
    
    col_load1, col_load2 = st.columns([3, 1])
    
    with col_load1:
        results_file = st.file_uploader(
            "Upload pushover results file",
            type=['pkl'],
            help="Select a .pkl file containing pushover results"
        )
    
    with col_load2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("📥 Load Results", key="load_pushover_results_btn"):
            if results_file is not None:
                try:
                    import pickle
                    results_data = pickle.load(results_file)
                    st.session_state.pushover_results = results_data
                    st.session_state.pushover_analysis_done = True
                    st.success("✅ Results loaded successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error loading results: {str(e)}")
            else:
                st.warning("⚠️ Please select a file first")
    
    # Check if results exist
    if not st.session_state.pushover_analysis_done or 'pushover_results' not in st.session_state:
        st.info("ℹ️ No results available. Either run an analysis in the Analysis tab or load results from a file.")
        return
    
    results = st.session_state.pushover_results
    dtecho = results['dtecho']
    Vbasal = results['Vbasal']
    drifts = results['drifts']
    rotations = results['rotations']
    coordy = results.get('coordy', [])
    tagcols = results.get('tagcols', [])
    tagbeams = results.get('tagbeams', [])
    
    # Display summary
    st.markdown("---")
    st.markdown("### 📊 Analysis Summary")
    
    col_sum1, col_sum2, col_sum3, col_sum4 = st.columns(4)
    
    with col_sum1:
        st.metric("Analysis Steps", len(dtecho))
    
    with col_sum2:
        st.metric("Max Base Shear", f"{max(Vbasal):.2f} kN")
    
    with col_sum3:
        st.metric("Max Roof Disp", f"{max(dtecho):.4f} m")
    
    with col_sum4:
        roof_drift = max(dtecho) / coordy[-1] if len(coordy) > 0 else 0
        st.metric("Max Roof Drift", f"{roof_drift*100:.2f}%")
    
    st.markdown("---")
    
    # Create sub-tabs for different plot types
    plot_tab1, plot_tab2, plot_tab3 = st.tabs([
        "📈 Pushover Curve",
        "📊 Capacity Curve",
        "🎯 Interactive Drift Analysis"
    ])
    
    with plot_tab1:
        st.markdown("### Pushover Curve (Base Shear vs Roof Displacement)")
        
        fig_pushover = go.Figure()
        fig_pushover.add_trace(go.Scatter(
            x=dtecho,
            y=Vbasal,
            mode='lines+markers',
            name='Pushover Curve',
            line=dict(color='blue', width=2),
            marker=dict(size=4)
        ))
        
        fig_pushover.update_layout(
            title="Pushover Curve",
            xaxis_title="Roof Displacement (m)",
            yaxis_title="Base Shear (kN)",
            height=600,
            hovermode='closest',
            showlegend=True
        )
        
        st.plotly_chart(fig_pushover, use_container_width=True)
    
    with plot_tab2:
        st.markdown("### Capacity Curve (Base Shear vs First Floor Drift)")
        
        if len(drifts) > 0:
            first_floor_drift = drifts[:len(Vbasal), 0]
            
            fig_capacity = go.Figure()
            fig_capacity.add_trace(go.Scatter(
                x=first_floor_drift,
                y=Vbasal,
                mode='lines+markers',
                name='Capacity Curve',
                line=dict(color='red', width=2),
                marker=dict(size=4)
            ))
            
            fig_capacity.update_layout(
                title="First Floor Drift vs Base Shear",
                xaxis_title="First Floor Drift Ratio",
                yaxis_title="Base Shear (kN)",
                height=600,
                hovermode='closest',
                showlegend=True
            )
            
            st.plotly_chart(fig_capacity, use_container_width=True)
        else:
            st.warning("⚠️ Drift data not available")
    
    with plot_tab3:
        st.markdown("### Interactive Drift Analysis")
        st.markdown("Select a roof drift ratio to visualize the drift profile and member rotations.")
        
        # Calculate available roof drifts
        if len(coordy) > 0 and len(dtecho) > 0:
            roof_drifts = [d / coordy[-1] for d in dtecho]
            
            # Drift selection slider - use index directly
            selected_idx = st.slider(
                "Select Time Step",
                min_value=0,
                max_value=len(dtecho) - 1,
                value=0,
                step=1,
                help="Slide to select a time step and view results",
                key="drift_time_step_slider"
            )
            
            # Use the selected index directly
            time_step = selected_idx
            
            # Verify time_step is within bounds for all arrays
            n_floors = len(coordy) - 1
            max_time_step = min(len(dtecho), len(Vbasal), drifts.shape[0] if len(drifts.shape) > 0 else 0) - 1
            time_step = min(time_step, max_time_step)
            
            # Display selected drift info
            selected_drift_value = roof_drifts[time_step]
            
            st.info(f"📍 **Selected:** Roof Drift = {selected_drift_value*100:.2f}% | Time Step = {time_step+1}/{len(dtecho)} | Roof Disp = {dtecho[time_step]:.4f} m | Base Shear = {Vbasal[time_step]:.2f} kN")
            
            # Create two columns for plots
            col_plot1, col_plot2 = st.columns([1, 1])
            
            with col_plot1:
                st.markdown("#### Drift Profile")
                
                # Extract drift profile for this time step
                # drifts array shape: [n_steps, n_floors] - each row is a time step, each column is a floor
                # As shown in master_script: story_drifts = drifts[:len(dtecho),:]
                drift_profile = drifts[time_step, :n_floors]  # Get row for this time step, limit to n_floors
                floor_heights = coordy[1:]
                
                # Create drift profile plot
                fig_drift_profile = go.Figure()
                
                fig_drift_profile.add_trace(go.Scatter(
                    x=drift_profile * 100,  # Convert to percentage
                    y=floor_heights,
                    mode='lines+markers',
                    name='Story Drift',
                    line=dict(color='green', width=3),
                    marker=dict(size=8, color='green')
                ))
                
                fig_drift_profile.update_layout(
                    title=f"Story Drift Profile at {selected_drift_value*100:.2f}% Roof Drift",
                    xaxis_title="Story Drift (%)",
                    yaxis_title="Height (m)",
                    xaxis=dict(range=[0, None]),  # Start x-axis at 0
                    height=500,
                    hovermode='closest',
                    showlegend=True
                )
                
                st.plotly_chart(fig_drift_profile, use_container_width=True)
            
            with col_plot2:
                st.markdown("#### Pushover Curve with Selected Point")
                
                # Create pushover curve with marker at selected point
                fig_pushover_marker = go.Figure()
                
                # Plot full curve
                fig_pushover_marker.add_trace(go.Scatter(
                    x=dtecho,
                    y=Vbasal,
                    mode='lines',
                    name='Pushover Curve',
                    line=dict(color='blue', width=2)
                ))
                
                # Add marker at selected point
                fig_pushover_marker.add_trace(go.Scatter(
                    x=[dtecho[time_step]],
                    y=[Vbasal[time_step]],
                    mode='markers',
                    name='Selected Point',
                    marker=dict(size=15, color='red', symbol='circle')
                ))
                
                fig_pushover_marker.update_layout(
                    title=f"Selected: {dtecho[time_step]:.4f} m, {Vbasal[time_step]:.2f} kN",
                    xaxis_title="Roof Displacement (m)",
                    yaxis_title="Base Shear (kN)",
                    height=500,
                    hovermode='closest',
                    showlegend=True
                )
                
                st.plotly_chart(fig_pushover_marker, use_container_width=True)
            
            # Building visualization with rotation scatter plot - MOVED BEFORE TABLES
            st.markdown("---")
            st.markdown("#### Building Frame with Member Rotations")
            
            if len(tagcols) > 0 and len(tagbeams) > 0:
                # Colormap selector
                col_cmap1, col_cmap2 = st.columns([3, 1])
                with col_cmap1:
                    colormap = st.selectbox(
                        "Select Colormap",
                        options=['RdYlGn_r', 'Reds', 'Blues', 'Greens', 'Viridis', 'Plasma', 'Inferno', 'Magma', 'Cividis', 'YlOrRd'],
                        index=0,
                        help="Choose color scale for rotation magnitude visualization",
                        key="rotation_colormap_selector"
                    )
                
                # Create building frame plot
                fig_building = go.Figure()
                
                # Get node coordinates from coordx and coordy
                # Try to get proper coordx if available
                if 'coordx' in results and results['coordx'] is not None:
                    coordx_local = results['coordx']
                elif st.session_state.get('coordx') is not None:
                    # Fallback: use session state if available
                    coordx_local = st.session_state.get('coordx')
                else:
                    # Last resort: use default values
                    coordx_local = [0, 5, 10]
                
                # Ensure coordx_local is not None
                if coordx_local is None:
                    coordx_local = [0, 5, 10]
                
                n_x_pos = len(coordx_local)
                n_spans = len(coordx_local) - 1
                
                # Get assignments if available
                column_assignments = results.get('column_assignments', st.session_state.get('column_assignments', {}))
                beam_assignments = results.get('beam_assignments', st.session_state.get('beam_assignments', {}))
                
                # Draw columns - only those that exist
                for floor_idx in range(n_floors):
                    floor_num = floor_idx + 1
                    y_bottom = coordy[floor_idx]
                    y_top = coordy[floor_idx + 1]
                    
                    for x_idx, x_pos in enumerate(coordx_local):
                        # Check if column exists at this location
                        if column_assignments and floor_num in column_assignments:
                            if x_idx in column_assignments[floor_num]:
                                if column_assignments[floor_num][x_idx] != 'None':
                                    # Draw column line
                                    fig_building.add_trace(go.Scatter(
                                        x=[x_pos, x_pos],
                                        y=[y_bottom, y_top],
                                        mode='lines',
                                        line=dict(color='blue', width=3),
                                        showlegend=False,
                                        hoverinfo='skip'
                                    ))
                        else:
                            # If no assignment data, draw all columns
                            fig_building.add_trace(go.Scatter(
                                x=[x_pos, x_pos],
                                y=[y_bottom, y_top],
                                mode='lines',
                                line=dict(color='blue', width=3),
                                showlegend=False,
                                hoverinfo='skip'
                            ))
                
                # Draw beams - only those that exist
                for floor_idx in range(n_floors):
                    floor_num = floor_idx + 1
                    y_level = coordy[floor_idx + 1]
                    
                    for span_idx in range(len(coordx_local) - 1):
                        # Check if beam exists at this location
                        if beam_assignments and floor_num in beam_assignments:
                            if span_idx in beam_assignments[floor_num]:
                                if beam_assignments[floor_num][span_idx] != 'None':
                                    x_left = coordx_local[span_idx]
                                    x_right = coordx_local[span_idx + 1]
                                    
                                    # Draw beam line
                                    fig_building.add_trace(go.Scatter(
                                        x=[x_left, x_right],
                                        y=[y_level, y_level],
                                        mode='lines',
                                        line=dict(color='red', width=3),
                                        showlegend=False,
                                        hoverinfo='skip'
                                    ))
                        else:
                            # If no assignment data, draw all beams
                            x_left = coordx_local[span_idx]
                            x_right = coordx_local[span_idx + 1]
                            
                            fig_building.add_trace(go.Scatter(
                                x=[x_left, x_right],
                                y=[y_level, y_level],
                                mode='lines',
                                line=dict(color='red', width=3),
                                showlegend=False,
                                hoverinfo='skip'
                            ))
                
                # Collect all rotation values for color scaling
                all_rotations = []
                rotation_data = []
                
                # Process column rotations
                for idx, col_tag in enumerate(tagcols):
                    if idx < len(rotations):
                        rot_i = abs(rotations[idx, time_step, 1])
                        rot_j = abs(rotations[idx, time_step, 2])
                        all_rotations.extend([rot_i, rot_j])
                        
                        # Determine column position
                        floor = idx // n_x_pos
                        x_pos_idx = idx % n_x_pos
                        
                        if floor < n_floors and x_pos_idx < len(coordx_local):
                            x = coordx_local[x_pos_idx]
                            y_bottom = coordy[floor]
                            y_top = coordy[floor + 1]
                            
                            # Display only initial rotation at bottom, offset upward
                            y_offset = 0.3
                            
                            rotation_data.append({
                                'x': x,
                                'y': y_bottom + y_offset,
                                'rotation': rot_i,
                                'label': f'{rot_i:.4f}',
                                'type': 'Column i'
                            })
                
                # Process beam rotations
                for idx, beam_tag in enumerate(tagbeams):
                    elem_idx = len(tagcols) + idx
                    if elem_idx < len(rotations):
                        rot_i = abs(rotations[elem_idx, time_step, 1])
                        rot_j = abs(rotations[elem_idx, time_step, 2])
                        all_rotations.extend([rot_i, rot_j])
                        
                        # Determine beam position
                        floor = idx // n_spans
                        span_idx = idx % n_spans
                        
                        if floor < n_floors and span_idx < len(coordx_local) - 1:
                            y = coordy[floor + 1]
                            x_left = coordx_local[span_idx]
                            x_right = coordx_local[span_idx + 1]
                            
                            # Offset for visibility - left node to the right, right node to the left
                            x_offset = 0.3
                            
                            rotation_data.append({
                                'x': x_left + x_offset,
                                'y': y,
                                'rotation': rot_i,
                                'label': f'{rot_i:.4f}',
                                'type': 'Beam i'
                            })
                            
                            rotation_data.append({
                                'x': x_right - x_offset,
                                'y': y,
                                'rotation': rot_j,
                                'label': f'{rot_j:.4f}',
                                'type': 'Beam j'
                            })
                
                # Add rotation scatter plot with color scale (NO TEXT LABELS)
                if rotation_data:
                    rot_df = pd.DataFrame(rotation_data)
                    
                    fig_building.add_trace(go.Scatter(
                        x=rot_df['x'],
                        y=rot_df['y'],
                        mode='markers',  # REMOVED 'text' mode
                        marker=dict(
                            size=12,
                            color=rot_df['rotation'],
                            colorscale=colormap,  # Use selected colormap
                            showscale=True,
                            colorbar=dict(
                                title="Rotation<br>(rad)",
                                x=1.15
                            ),
                            cmin=0,
                            cmax=max(all_rotations) if all_rotations else 0.01
                        ),
                        name='Rotations',
                        hovertemplate='<b>Rotation: %{customdata[0]:.6f} rad</b><br>Type: %{customdata[1]}<br>X: %{x:.2f} m<br>Y: %{y:.2f} m<extra></extra>',
                        customdata=list(zip(rot_df['label'], rot_df['type']))
                    ))
                
                fig_building.update_layout(
                    title=f"Building Frame - Member Rotations at {selected_drift_value*100:.2f}% Roof Drift",
                    xaxis_title="X Position (m)",
                    yaxis_title="Height (m)",
                    height=600,
                    showlegend=False,
                    hovermode='closest',
                    xaxis=dict(scaleanchor="y", scaleratio=1),
                    yaxis=dict(scaleanchor="x", scaleratio=1)
                )
                
                st.plotly_chart(fig_building, use_container_width=True)
            else:
                st.warning("⚠️ Element tag information not available")
            
            # Member rotations tables - NOW AFTER BUILDING PLOT
            st.markdown("---")
            st.markdown("#### Member Rotation Tables")
            
            if len(tagcols) > 0 and len(tagbeams) > 0:
                rot_tab1, rot_tab2 = st.tabs(["Column Rotations", "Beam Rotations"])
                
                with rot_tab1:
                    st.markdown("**Column Rotations**")
                    
                    # Extract column rotations for this time step
                    # rotations shape: [n_elements, n_steps, 3] where last dim is [axial_def, rot_i, rot_j]
                    # As shown in master_script: column_rotations = rotations[:len(tagcols),:len(dtecho),[1,2]]
                    # Index [1,2] means we want rotations (skip axial deformation at index 0)
                    
                    # Group columns by floor
                    col_data = []
                    for idx, col_tag in enumerate(tagcols):
                        if idx < len(rotations):
                            rot_i = rotations[idx, time_step, 1]  # Rotation at end i (index 1)
                            rot_j = rotations[idx, time_step, 2]  # Rotation at end j (index 2)
                        
                            # Determine floor (simplified - assumes sequential tagging)
                            floor_num = (idx // (len(coordy) - 1)) + 1 if len(coordy) > 1 else 1
                            
                            col_data.append({
                                'Column Tag': col_tag,
                                'Floor': min(floor_num, n_floors),
                                'Rotation i (rad)': rot_i
                            })
                    
                    col_df = pd.DataFrame(col_data)
                    st.dataframe(col_df, use_container_width=True, hide_index=True, height=400)
                    
                    # Export button
                    csv_col = col_df.to_csv(index=False)
                    st.download_button(
                        label="💾 Download Column Rotations CSV",
                        data=csv_col,
                        file_name=f"column_rotations_drift_{selected_drift_value*100:.2f}pct.csv",
                        mime="text/csv"
                    )
                
                with rot_tab2:
                    st.markdown("**Beam Rotations**")
                    
                    # Extract beam rotations for this time step
                    # Beams start after columns in the rotations array
                    
                    # Group beams by floor
                    beam_data = []
                    for idx, beam_tag in enumerate(tagbeams):
                        elem_idx = len(tagcols) + idx  # Beam index in rotations array
                        if elem_idx < len(rotations):
                            rot_i = rotations[elem_idx, time_step, 1]  # Rotation at end i (index 1)
                            rot_j = rotations[elem_idx, time_step, 2]  # Rotation at end j (index 2)
                            
                            # Determine floor
                            floor_num = (idx // max(1, len(coordy) - 2)) + 1 if len(coordy) > 1 else 1
                            
                            beam_data.append({
                                'Beam Tag': beam_tag,
                                'Floor': min(floor_num, n_floors),
                                'Rotation i (rad)': rot_i,
                                'Rotation j (rad)': rot_j
                            })
                    
                    beam_df = pd.DataFrame(beam_data)
                    st.dataframe(beam_df, use_container_width=True, hide_index=True, height=400)
                    
                    # Export button
                    csv_beam = beam_df.to_csv(index=False)
                    st.download_button(
                        label="💾 Download Beam Rotations CSV",
                        data=csv_beam,
                        file_name=f"beam_rotations_drift_{selected_drift_value*100:.2f}pct.csv",
                        mime="text/csv"
                    )
            else:
                st.warning("⚠️ Element tag information not available")
        else:
            st.warning("⚠️ Building geometry information not available")


# ==================== TAB 8: PYTHON SCRIPT ====================
def render_python_script_tab():
    """Render Python Script generation tab"""
    st.header("Python Script Generator")
    st.markdown("Generate a Python script matching your app configuration to compare with master_script_pushover.py")
    
    if not st.session_state.model_created:
        st.warning("⚠️ Please create the model first.")
        return
    elif not st.session_state.elements_created:
        st.warning("⚠️ Please create structural elements first.")
        return
    
    st.markdown("---")
    st.markdown("### 📝 Generate Python Script")
    st.info("This script replicates your current model configuration and can be run independently in any Python environment with OpenSeesPy.")
    
    n_floors = len(st.session_state.coordy) - 1
    n_x_positions = len(st.session_state.coordx)
    n_spans = len(st.session_state.coordx) - 1
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        script_filename = st.text_input(
            "Script filename",
            value="generated_model.py",
            help="Name for the Python script file"
        )
    
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        generate_button = st.button("🐛 Generate Script", type="primary", key="generate_debug_script")
    
    if generate_button:
        try:
            # Build comprehensive debug script using the function
            debug_script = generate_debug_script_from_state(st.session_state, n_floors, n_x_positions, n_spans)
            
            # Store in session state to persist
            st.session_state.generated_script = debug_script
            st.success("✅ Script generated successfully!")
        except Exception as e:
            st.error(f"❌ Error generating script: {str(e)}")
            import traceback
            st.code(traceback.format_exc())
    
    # Display the script if it exists
    if 'generated_script' in st.session_state:
        st.markdown("---")
        st.markdown("### 📄 Generated Script")
        
        # Display the script
        st.code(st.session_state.generated_script, language='python', line_numbers=True)
        
        # Provide download button
        st.download_button(
            label="💾 Download Python Script",
            data=st.session_state.generated_script,
            file_name=script_filename,
            mime="text/x-python",
            type="primary"
        )


# ==================== TAB 9: ANALYSIS ====================
def render_analysis_tab():
    """Render Analysis tab for 2D model (Gravity + Pushover)"""
    st.header("Structural Analysis")
    st.markdown("Run gravity and pushover analyses on the 2D building model.")
    
    st.markdown("---")
    
    # Gravity Analysis
    st.markdown("### 1. Gravity Analysis")
    st.markdown("Run static analysis under gravity loads to establish initial state.")
    
    if st.session_state.gravity_analysis_done:
        st.success("✅ Gravity analysis completed!")
    else:
        if st.button("⚙️ Run Gravity Analysis", type="primary", key="run_gravity_2d"):
            try:
                with st.spinner("Running gravity analysis..."):
                    an.gravedad()
                    loadConst('-time', 0.0)
                    st.session_state.gravity_analysis_done = True
                    st.success("✅ Gravity analysis completed successfully!")
                    st.rerun()
            except Exception as e:
                st.error(f"❌ Error in gravity analysis: {str(e)}")
                import traceback
                st.code(traceback.format_exc())
    
    st.markdown("---")
    
    # Pushover Analysis
    st.markdown("### 2. Pushover Analysis")
    st.markdown("Nonlinear static pushover analysis with lateral load pattern.")
    
    if not st.session_state.gravity_analysis_done:
        st.info("ℹ️ Please run gravity analysis first before pushover.")
    else:
        st.markdown("#### Pushover Parameters")
        
        col_push1, col_push2 = st.columns(2)
        
        with col_push1:
            # Target drift
            max_height = st.session_state.coordy[-1]
            target_drift_ratio = st.number_input(
                "Target Drift Ratio (%)",
                min_value=0.1,
                max_value=10.0,
                value=5.0,
                step=0.5,
                help="Maximum drift as percentage of building height"
            )
            target_displacement = (target_drift_ratio / 100.0) * max_height
            st.info(f"📏 Target displacement: {target_displacement:.3f} m")
            
            increment = st.number_input(
                "Displacement Increment (m)",
                min_value=0.0001,
                max_value=0.1,
                value=0.001,
                step=0.0001,
                format="%.4f",
                help="Step size for displacement control"
            )
        
        with col_push2:
            # Control node selection - use highest node (as in master_script)
            st.markdown("**Control Node:**")
            
            # Get the highest node tag (roof node with highest tag number)
            all_node_tags = getNodeTags()
            control_node = all_node_tags[-1]  # Last node (highest tag) as in master_script
            
            st.info(f"🎯 Control node: {control_node} (roof - highest node tag)")
            st.caption("Following master_script logic: uses getNodeTags()[-1]")
        
        st.markdown("---")
        
        if st.session_state.pushover_analysis_done:
            st.success("✅ Pushover analysis completed!")
            
            # Plot results if available
            if hasattr(st.session_state, 'pushover_results'):
                st.markdown("### 📊 Pushover Results")
                
                results = st.session_state.pushover_results
                dtecho = results['dtecho']
                Vbasal = results['Vbasal']
                drifts = results['drifts']
                
                # Pushover curve
                fig_pushover = go.Figure()
                fig_pushover.add_trace(go.Scatter(
                    x=dtecho,
                    y=Vbasal,
                    mode='lines+markers',
                    name='Pushover Curve',
                    line=dict(color='blue', width=2),
                    marker=dict(size=4)
                ))
                
                fig_pushover.update_layout(
                    title="Pushover Curve",
                    xaxis_title="Roof Displacement (m)",
                    yaxis_title="Base Shear (kN)",
                    height=500,
                    hovermode='closest',
                    showlegend=True
                )
                
                st.plotly_chart(fig_pushover, use_container_width=True, key="pushover_curve")
                
                # First Floor Drift vs Base Shear
                if len(drifts) > 0:
                    st.markdown("### 📈 First Floor Drift vs Base Shear")
                    
                    # Get first floor drift - EXACTLY as in master_script: drifts[:len(Vbasal),0]
                    first_floor_drift = drifts[:len(Vbasal), 0]
                    
                    fig_drift_capacity = go.Figure()
                    
                    fig_drift_capacity.add_trace(go.Scatter(
                        x=first_floor_drift,
                        y=Vbasal,
                        mode='lines+markers',
                        name='Capacity Curve',
                        line=dict(color='red', width=2),
                        marker=dict(size=4)
                    ))
                    
                    fig_drift_capacity.update_layout(
                        title="First Floor Drift vs Base Shear (Capacity Curve)",
                        xaxis_title="First Floor Drift Ratio",
                        yaxis_title="Base Shear (kN)",
                        height=500,
                        hovermode='closest',
                        showlegend=True
                    )
                    
                    st.plotly_chart(fig_drift_capacity, use_container_width=True, key="drift_capacity_curve")
                
                # Save pushover results button
                st.markdown("---")
                st.markdown("### 💾 Save Pushover Results")
                
                col_save1, col_save2 = st.columns([3, 1])
                with col_save1:
                    results_filename = st.text_input(
                        "Results filename",
                        value="pushover_results.pkl",
                        help="Name for the pushover results file"
                    )
                
                with col_save2:
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button("💾 Save Results", type="primary", key="save_pushover_results"):
                        try:
                            import pickle
                            # Create Pushover Results folder if it doesn't exist
                            results_folder = os.path.join(os.getcwd(), "Pushover Results")
                            os.makedirs(results_folder, exist_ok=True)
                            
                            results_path = os.path.join(results_folder, results_filename)
                            with open(results_path, 'wb') as f:
                                pickle.dump(st.session_state.pushover_results, f)
                            st.success(f"✅ Results saved to: {results_path}")
                        except Exception as e:
                            st.error(f"❌ Error saving results: {str(e)}")
                
        else:
            if st.button("🚀 Run Pushover Analysis", type="primary", key="run_pushover_2d"):
                try:
                    with st.spinner("Running pushover analysis... This may take a while."):
                        # Apply pushover loads (same as master_script)
                        leftmost_nodes_list = ut.find_leftmost_nodes(st.session_state.coordy)
                        ut.pushover_loads(st.session_state.coordy, nodes=leftmost_nodes_list)
                        
                        # Run pushover - ensure all tags are integers (same setup as master_script)
                        elements = [int(tag) for tag in st.session_state.tagcols] + [int(tag) for tag in st.session_state.tagbeams]
                        nodes_control = [1000] + [int(node) for node in leftmost_nodes_list]
                        control_node_int = int(control_node)  # This is getNodeTags()[-1]
                        
                        # Debug output before running
                        st.info("🐛 **Pushover Parameters:**")
                        st.write(f"- target_displacement: {target_displacement}")
                        st.write(f"- increment: {increment}")
                        st.write(f"- control_node: {control_node_int}")
                        st.write(f"- direction: 1 (X)")
                        st.write(f"- leftmost_nodes: {leftmost_nodes_list}")
                        st.write(f"- nodes_control: {nodes_control}")
                        st.write(f"- elements count: {len(elements)} (cols: {len(st.session_state.tagcols)}, beams: {len(st.session_state.tagbeams)})")
                        st.write(f"- elements (first 10): {elements[:10]}")
                        
                        dtecho, Vbasal, drifts, rotations = an.pushover2DRot(
                            target_displacement,
                            increment,
                            control_node_int,
                            1,  # direction (1 for X)
                            nodes_control,
                            elements
                        )
                        
                        # Prepare mass dataframe and building weight
                        node_masses = st.session_state.get('node_masses', {})
                        mass_df = None
                        building_weight = 0.0
                        
                        if node_masses:
                            # Create mass dataframe from node_masses dict
                            mass_data = []
                            total_mass = 0.0
                            for node_tag in sorted(node_masses.keys()):
                                mass_val = node_masses[node_tag]
                                mass_data.append({
                                    'Node': int(node_tag),
                                    'Mass (ton)': mass_val
                                })
                                total_mass += mass_val
                            
                            mass_df = pd.DataFrame(mass_data)
                            building_weight = total_mass * 9.81  # Convert ton to kN
                        
                        # Store results (including coordx, coordy and element info for post-processing)
                        st.session_state.pushover_results = {
                            'dtecho': dtecho,
                            'Vbasal': Vbasal,
                            'drifts': drifts,
                            'rotations': rotations,
                            'control_node': control_node,
                            'target_displacement': target_displacement,
                            'coordx': st.session_state.coordx,
                            'coordy': st.session_state.coordy,
                            'column_assignments': st.session_state.column_assignments,
                            'beam_assignments': st.session_state.beam_assignments,
                            'tagcols': st.session_state.tagcols,
                            'tagbeams': st.session_state.tagbeams,
                            'increment': increment,
                            'mass_df': mass_df,
                            'building_weight': building_weight
                        }
                        st.session_state.pushover_analysis_done = True
                        
                        st.success("✅ Pushover analysis completed successfully!")
                        st.success(f"📊 Analysis steps: {len(dtecho)}")
                        st.rerun()
                        
                except Exception as e:
                    st.error(f"❌ Error in pushover analysis: {str(e)}")
                    import traceback
                    st.code(traceback.format_exc())


# ==================== MAIN APPLICATION ====================
def main():
    """
    Main application entry point for the 2D Building Analysis App.

    Application Structure:
    ---------------------
    1. Page Configuration: Wide layout, custom title and icon
    2. Session State: Initialize all required state variables
    3. Tab Interface: 9 tabs for sequential workflow
    4. Content Rendering: Call appropriate render functions for each tab

    Tab Sequence:
    -------------
    0. Load/New Model - Start new or load existing
    1. Building Geometry - Define 2D coordinates
    2. Materials - Create concrete/steel material sets
    3. Sections - Define cross-sectional properties
    4. Element Assignment - Assign sections to columns and beams
    5. Model Visualization - Review and create elements
    6. Loads and Mass Assignments - Apply loads, masses, and nodal loads
    7. Save Model - Export for analysis
    8. Python Script - Generate standalone script
    9. Modal Analysis - Compute natural frequencies and mode shapes
    10. Analysis - Gravity + Pushover analysis
    11. Pushover Results - Visualize analysis results
    """
    # Page configuration
    st.set_page_config(
        page_title="2D Building Analysis",
        page_icon="🏢",
        layout="wide"
    )
    
    st.title("🏢 2D Building Analysis with OpenSeesPy")
    st.markdown("Create and analyze planar RC frame structures")
    st.markdown("---")
    
    # Initialize session state
    initialize_session_state()
    
    # Create tabs
    tab0, tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10, tab11, tab12, tab13 = st.tabs([
        "Load/New Model",
        "Building Geometry",
        "Materials",
        "Masonry Materials",
        "Sections",
        "Element Assignment",
        "Model Visualization",
        "Infill Assignment",
        "Loads and Mass Assignments",
        "Save Model",
        "Python Script",
        "Modal Analysis",
        "Analysis",
        "Pushover Results"
    ])

    with tab0:
        render_load_model_tab()

    with tab1:
        render_geometry_tab()

    with tab2:
        render_materials_tab()

    with tab3:
        render_masonry_materials_tab()

    with tab4:
        render_sections_tab()

    with tab5:
        render_assignment_tab()

    with tab6:
        render_model_visualization_tab()

    with tab7:
        render_infill_assignment_tab()

    with tab8:
        render_loads_and_masses_tab()

    with tab9:
        render_save_model_tab()

    with tab10:
        render_python_script_tab()

    with tab11:
        render_modal_analysis_tab()

    with tab12:
        render_analysis_tab()

    with tab13:
        render_pushover_results_tab()


if __name__ == "__main__":
    main()
