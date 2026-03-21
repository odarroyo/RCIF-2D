"""
2D RC Building Analysis - Library Module
=========================================

Reusable functions for 2D RC frame building analysis application.
This module contains utility functions for model creation, visualization,
and data processing that are independent of the Streamlit UI.

Author: Generated for 2D RC frame pushover analysis
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from openseespy.opensees import *
import opseestools.utilidades as ut


# ==================== CONSTANTS ====================
REBAR_AREAS = {
    'As4': 0.000127,  # #4 diameter rebar
    'As5': 0.0002,    # #5 diameter rebar
    'As6': 0.000286,   # #6 diameter rebar
    'As7': 0.000387,   # #7 diameter rebar
    'As8': 0.000508   # #8 diameter rebar
}

DETAILING_OPTIONS = ["DES", "DMO", "PreCode"]


# ==================== GEOMETRY FUNCTIONS ====================
def parse_coordinates(coord_input):
    """
    Parse comma-separated coordinate string into list of floats.
    
    Parameters
    ----------
    coord_input : str
        Comma-separated coordinate values (e.g., "0, 5.0, 12.0")
    
    Returns
    -------
    list
        List of float coordinate values
    """
    return [float(x.strip()) for x in coord_input.split(',')]


def create_opensees_model(coordx, coordy):
    """
    Create 2D OpenSeesPy model with geometry.
    
    Parameters
    ----------
    coordx : list
        X coordinates of the grid
    coordy : list
        Y coordinates of the grid (floor heights)
    """
    wipe()
    model('basic', '-ndm', 2, '-ndf', 3)
    ut.creategrid(coordx, coordy)
    fixY(0, 1, 1, 1)


# ==================== MATERIAL FUNCTIONS ====================
def generate_material_tags(material_index):
    """
    Generate unique OpenSeesPy tags for material components.
    
    Parameters
    ----------
    material_index : int
        Index of the material in the materials list
    
    Returns
    -------
    dict
        Dictionary with 'unctag', 'conftag', 'steeltag' keys
    """
    base_tag = (material_index + 1) * 100
    return {
        'unctag': base_tag + 1,
        'conftag': base_tag + 2,
        'steeltag': base_tag + 3
    }


def create_material(fc, fy, detailing, material_index):
    """
    Create OpenSeesPy material and return material properties.
    
    Parameters
    ----------
    fc : float
        Concrete compressive strength (MPa)
    fy : float
        Steel yield strength (MPa)
    detailing : str
        Detailing level ('DES', 'DMO', or 'PreCode')
    material_index : int
        Index for unique tag generation
    
    Returns
    -------
    dict
        Material properties including tags and parameters
    """
    tags = generate_material_tags(material_index)
    
    noconf, conf, acero = ut.col_materials(
        fc, fy,
        detailing=detailing,
        nps=3,
        unctag=tags['unctag'],
        conftag=tags['conftag'],
        steeltag=tags['steeltag']
    )
    
    return {
        'fc': fc,
        'fy': fy,
        'detailing': detailing,
        'noconf_tag': noconf,
        'conf_tag': conf,
        'acero_tag': acero
    }


# ==================== SECTION FUNCTIONS ====================
def generate_section_tag(section_index):
    """
    Generate unique tag for section.
    
    Parameters
    ----------
    section_index : int
        Index of the section
    
    Returns
    -------
    int
        Unique section tag
    """
    return (section_index + 1) * 100 + 1000


def create_section(section_tag, H, B, cover, material_props, bars_config):
    """
    Create rectangular RC section in OpenSeesPy.
    
    Parameters
    ----------
    section_tag : int
        Unique tag for the section
    H : float
        Section height (m)
    B : float
        Section base width (m)
    cover : float
        Concrete cover (m)
    material_props : dict
        Material properties dictionary with tag information
    bars_config : dict
        Reinforcement configuration with keys:
        'bars_top', 'area_top', 'bars_bottom', 'area_bottom',
        'bars_middle', 'area_middle'
    """
    if bars_config['bars_middle'] == 0:
        ut.create_rect_RC_section(
            section_tag, H, B, cover,
            material_props['conf_tag'],
            material_props['noconf_tag'],
            material_props['acero_tag'],
            bars_config['bars_top'],
            bars_config['area_top'],
            bars_config['bars_bottom'],
            bars_config['area_bottom']
        )
    else:
        ut.create_rect_RC_section(
            section_tag, H, B, cover,
            material_props['conf_tag'],
            material_props['noconf_tag'],
            material_props['acero_tag'],
            bars_config['bars_top'],
            bars_config['area_top'],
            bars_config['bars_bottom'],
            bars_config['area_bottom'],
            bars_config['bars_middle'],
            bars_config['area_middle']
        )


# ==================== ASSIGNMENT FUNCTIONS ====================
def build_element_tags_list_2d(assignments, sections, num_floors, num_positions):
    """
    Build list of section tags for 2D elements.
    
    Parameters
    ----------
    assignments : dict
        {floor: {position: section_name}}
    sections : dict
        Section definitions
    num_floors : int
        Number of floors
    num_positions : int
        Number of positions (columns or beams)
    
    Returns
    -------
    list
        Nested list [floor][position] with section tags
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


def rebuild_model_from_state(coordx, coordy, materials, sections,
                              column_assignments, beam_assignments,
                              floor_diaphragms, load_type, load_data,
                              node_masses, node_loads):
    """
    Rebuild the entire OpenSeesPy model from session state for a clean analysis.

    This ensures the C-level model state is identical to what a standalone script
    would produce (wipe → full sequential build), avoiding any accumulated state
    from the incremental Streamlit workflow.

    Parameters
    ----------
    coordx : list
        X coordinates
    coordy : list
        Y coordinates
    materials : dict
        Material definitions {name: {fc, fy, detailing, noconf_tag, conf_tag, acero_tag}}
    sections : dict
        Section definitions {name: {tag, H, B, cover, material, bars_*, area_*}}
    column_assignments : dict
        {floor: {x_idx: section_name}}
    beam_assignments : dict
        {floor: {span_idx: section_name}}
    floor_diaphragms : list
        List of 0/1 per floor
    load_type : str
        'same' or 'beamwise'
    load_data : dict
        Load parameters (floor_beam_loads, roof_beam_loads, or beam_loads)
    node_masses : dict
        {node_tag: mass_value}
    node_loads : dict
        {node_tag: {Fx, Fy, Mz}}

    Returns
    -------
    tuple
        (tagcols, tagbeams) - element tag lists
    """
    import opseestools.analisis as an

    # 1. Clean slate
    wipe()
    model('basic', '-ndm', 2, '-ndf', 3)
    ut.creategrid(coordx, coordy)
    fixY(0, 1, 1, 1)

    # 2. Recreate materials with the exact same tags as original
    for mat_name, mat_props in materials.items():
        ut.col_materials(
            mat_props['fc'], mat_props['fy'],
            detailing=mat_props['detailing'],
            nps=3,
            unctag=mat_props['noconf_tag'],
            conftag=mat_props['conf_tag'],
            steeltag=mat_props['acero_tag']
        )

    # 3. Recreate sections
    # Note: session state stores rebar areas as string names ('As6', etc.)
    # Must convert to float values via REBAR_AREAS before passing to OpenSeesPy
    def _resolve_area(area_val):
        """Convert rebar area: string name -> float, or pass through if already float."""
        if isinstance(area_val, str):
            return REBAR_AREAS[area_val]
        return area_val

    for sec_name, sec_props in sections.items():
        mat_props = materials[sec_props['material']]
        cover = sec_props.get('cover', 0.05)
        area_top = _resolve_area(sec_props['area_top'])
        area_bottom = _resolve_area(sec_props['area_bottom'])

        if sec_props.get('bars_middle', 0) == 0:
            ut.create_rect_RC_section(
                sec_props['tag'], sec_props['H'], sec_props['B'], cover,
                mat_props['conf_tag'], mat_props['noconf_tag'], mat_props['acero_tag'],
                sec_props['bars_top'], area_top,
                sec_props['bars_bottom'], area_bottom
            )
        else:
            area_middle = _resolve_area(sec_props['area_middle'])
            ut.create_rect_RC_section(
                sec_props['tag'], sec_props['H'], sec_props['B'], cover,
                mat_props['conf_tag'], mat_props['noconf_tag'], mat_props['acero_tag'],
                sec_props['bars_top'], area_top,
                sec_props['bars_bottom'], area_bottom,
                sec_props['bars_middle'], area_middle
            )

    # 4. Create elements
    n_floors = len(coordy) - 1
    n_x = len(coordx)
    n_spans = len(coordx) - 1
    building_columns = build_element_tags_list_2d(column_assignments, sections, n_floors, n_x)
    building_beams = build_element_tags_list_2d(beam_assignments, sections, n_floors, n_spans)
    tagcols, tagbeams, col_info, beam_info = ut.create_elements2(
        coordx, coordy, building_columns, building_beams, output=1
    )
    ut.remove_hanging_nodes(tagcols, tagbeams)

    # 5. Diaphragms
    if floor_diaphragms and sum(floor_diaphragms) > 0:
        ut.apply_diaphragms(floor_diaphragms, output=1)

    # 6. Loads
    if load_type == 'same':
        ut.load_beams(
            -load_data['floor_beam_loads'],
            -load_data['roof_beam_loads'],
            tagbeams
        )
    else:
        beam_loads = load_data.get('beam_loads', [])
        if beam_loads:
            ut.load_beams2(beam_loads, tagbeams, output=1)

    # 7. Masses
    for node_tag, mass_val in node_masses.items():
        if mass_val > 0:
            mass(int(node_tag), mass_val, mass_val, 0.0)

    # 8. Nodal loads (if any)
    for node_tag, loads in node_loads.items():
        if loads['Fx'] != 0 or loads['Fy'] != 0 or loads['Mz'] != 0:
            load(int(node_tag), loads['Fx'], loads['Fy'], loads['Mz'])

    return tagcols, tagbeams


# ==================== VISUALIZATION FUNCTIONS ====================
def create_2d_frame_figure(coordx, coordy, column_assignments, beam_assignments, sections):
    """
    Create 2D frame elevation visualization with assigned sections.
    
    Parameters
    ----------
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
    
    Returns
    -------
    plotly.graph_objects.Figure
        Interactive 2D frame visualization
    """
    fig = go.Figure()
    
    # Generate unique colors for each section
    section_names = list(set([
        s for floor_dict in column_assignments.values() 
        for s in floor_dict.values() if s and s != 'None'
    ] + [
        s for floor_dict in beam_assignments.values() 
        for s in floor_dict.values() if s and s != 'None'
    ]))
    
    colors = ['#e6194b', '#3cb44b', '#ffe119', '#4363d8', '#f58231', 
              '#911eb4', '#46f0f0', '#f032e6', '#bcf60c', '#fabebe',
              '#008080', '#e6beff', '#9a6324', '#fffac8', '#800000',
              '#aaffc3', '#808000', '#ffd8b1', '#000075', '#808080']
    section_colors = {name: colors[i % len(colors)] for i, name in enumerate(section_names)}
    
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
                color = section_colors.get(section_name, 'blue')
                show_legend = section_name not in legend_added
                
                fig.add_trace(go.Scatter(
                    x=[x, x], y=[y_bot, y_top],
                    mode='lines',
                    line=dict(color=color, width=4),
                    name=section_name,
                    legendgroup=section_name,
                    showlegend=show_legend,
                    hovertemplate=f'Column<br>Section: {section_name}<br>Floor: {floor}<br>X: {x:.2f}m<extra></extra>'
                ))
                
                if show_legend:
                    legend_added.add(section_name)
    
    # Draw beams
    for floor in range(1, n_floors + 1):
        y = coordy[floor]
        
        for span_idx in range(n_spans):
            x1 = coordx[span_idx]
            x2 = coordx[span_idx + 1]
            section_name = beam_assignments.get(floor, {}).get(span_idx, 'None')
            
            if section_name and section_name != 'None':
                color = section_colors.get(section_name, 'red')
                show_legend = section_name not in legend_added
                
                fig.add_trace(go.Scatter(
                    x=[x1, x2], y=[y, y],
                    mode='lines',
                    line=dict(color=color, width=4),
                    name=section_name,
                    legendgroup=section_name,
                    showlegend=show_legend,
                    hovertemplate=f'Beam<br>Section: {section_name}<br>Floor: {floor}<br>Span: {span_idx+1}<extra></extra>'
                ))
                
                if show_legend:
                    legend_added.add(section_name)
    
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
        yaxis=dict(showgrid=True, gridcolor='lightgray', zeroline=True, 
                   scaleanchor='x', scaleratio=1)
    )
    
    return fig


def create_section_visualization(H, B, cover, bars_top, bars_bottom, bars_middle):
    """
    Create visualization of RC section with reinforcement layout.
    
    Parameters
    ----------
    H : float
        Section height (m)
    B : float
        Section base width (m)
    cover : float
        Concrete cover (m)
    bars_top : int
        Number of top reinforcement bars
    bars_bottom : int
        Number of bottom reinforcement bars
    bars_middle : int
        Number of middle/side reinforcement bars
    
    Returns
    -------
    plotly.graph_objects.Figure
        Section visualization
    """
    fig = go.Figure()
    
    # Draw section outline
    fig.add_trace(go.Scatter(
        x=[0, B, B, 0, 0],
        y=[0, 0, H, H, 0],
        mode='lines',
        line=dict(color='black', width=2),
        fill='toself',
        fillcolor='lightgray',
        name='Concrete',
        showlegend=True
    ))
    
    # Draw cover lines
    fig.add_trace(go.Scatter(
        x=[cover, B-cover, B-cover, cover, cover],
        y=[cover, cover, H-cover, H-cover, cover],
        mode='lines',
        line=dict(color='blue', width=1, dash='dash'),
        name='Cover',
        showlegend=True
    ))
    
    # Calculate bar positions
    bar_diameter = 0.02  # Visual representation
    
    # Top bars
    if bars_top > 1:
        top_x = np.linspace(cover, B - cover, bars_top)
    else:
        top_x = [B / 2]
    
    top_y = [H - cover] * len(top_x)
    
    # Bottom bars
    if bars_bottom > 1:
        bottom_x = np.linspace(cover, B - cover, bars_bottom)
    else:
        bottom_x = [B / 2]
    
    bottom_y = [cover] * len(bottom_x)
    
    # Middle bars (sides)
    middle_x = []
    middle_y = []
    if bars_middle > 0:
        # Distribute on left and right sides
        bars_per_side = bars_middle // 2
        if bars_per_side > 0:
            side_y = np.linspace(cover, H - cover, bars_per_side + 2)[1:-1]
            middle_x.extend([cover] * bars_per_side)
            middle_y.extend(side_y)
            middle_x.extend([B - cover] * bars_per_side)
            middle_y.extend(side_y)
    
    # Draw bars
    fig.add_trace(go.Scatter(
        x=top_x, y=top_y,
        mode='markers',
        marker=dict(size=10, color='red', symbol='circle'),
        name='Top Bars',
        showlegend=True
    ))
    
    fig.add_trace(go.Scatter(
        x=bottom_x, y=bottom_y,
        mode='markers',
        marker=dict(size=10, color='red', symbol='circle'),
        name='Bottom Bars',
        showlegend=True
    ))
    
    if middle_x:
        fig.add_trace(go.Scatter(
            x=middle_x, y=middle_y,
            mode='markers',
            marker=dict(size=10, color='red', symbol='circle'),
            name='Side Bars',
            showlegend=True
        ))
    
    # Add dimensions
    fig.add_annotation(
        x=B/2, y=-0.05,
        text=f'B = {B*1000:.0f} mm',
        showarrow=False,
        font=dict(size=12)
    )
    
    fig.add_annotation(
        x=-0.05, y=H/2,
        text=f'H = {H*1000:.0f} mm',
        showarrow=False,
        font=dict(size=12),
        textangle=-90
    )
    
    fig.update_layout(
        title=f"Section: {H*1000:.0f}×{B*1000:.0f} mm | Cover: {cover*1000:.0f} mm",
        xaxis=dict(
            scaleanchor="y", scaleratio=1,
            showgrid=False, zeroline=False,
            range=[-0.1, B + 0.1]
        ),
        yaxis=dict(
            showgrid=False, zeroline=False,
            range=[-0.1, H + 0.1]
        ),
        height=500,
        showlegend=True,
        hovermode='closest'
    )
    
    return fig


# ==================== DATA PROCESSING ====================
def validate_model_data(model_data):
    """
    Validate loaded model data structure.
    
    Parameters
    ----------
    model_data : dict
        Model data dictionary
    
    Returns
    -------
    tuple
        (is_valid, error_message)
    """
    required_keys = ['coordx', 'coordy', 'materials', 'sections', 
                     'column_assignments', 'beam_assignments']
    
    for key in required_keys:
        if key not in model_data:
            return False, f"Missing required key: {key}"
    
    # Check if it's a 3D model (should not have coordz)
    if 'coordz' in model_data:
        return False, "This appears to be a 3D model file"
    
    return True, ""


def prepare_model_export_data(session_state):
    """
    Prepare model data for export/saving.
    
    Parameters
    ----------
    session_state : dict or object
        Session state object or dictionary
    
    Returns
    -------
    dict
        Model data ready for pickling
    """
    model_data = {
        'project_name': getattr(session_state, 'project_name', 'building_2d'),
        'coordx': getattr(session_state, 'coordx', None),
        'coordy': getattr(session_state, 'coordy', None),
        'materials': getattr(session_state, 'materials', {}),
        'sections': getattr(session_state, 'sections', {}),
        'column_assignments': getattr(session_state, 'column_assignments', {}),
        'beam_assignments': getattr(session_state, 'beam_assignments', {}),
        'model_created': getattr(session_state, 'model_created', False),
        'elements_created': getattr(session_state, 'elements_created', False),
        'loads_applied': getattr(session_state, 'loads_applied', False),
    }
    
    # Add load data if exists
    if model_data['loads_applied']:
        load_type = getattr(session_state, 'load_type', 'same')
        model_data['load_type'] = load_type
        
        if load_type == 'same':
            model_data['floor_beam_loads'] = getattr(session_state, 'floor_beam_loads', None)
            model_data['roof_beam_loads'] = getattr(session_state, 'roof_beam_loads', None)
        else:
            model_data['beam_loads_beamwise'] = getattr(session_state, 'beam_loads_beamwise', {})
    
    return model_data

def dinamicoIDA4PRotRes(recordName,dtrec,nPts,dtan,fact,damp,IDctrlNode,IDctrlDOF,elements,nodes_control,modes = [0,2],Kswitch = 1,Tol=1e-4):
    '''
    Performs a dynamic analysis for a ground motion, recording information about displacements, velocity, accelerations, forces. Only allows elements with six DOF.

    Parameters
    ----------
    recordName : string
        Name of the record including file extension (i.e., 'GM01.txt'). It must have one record instant per line. 
    dtrec : float
        time increment of the record.
    nPts : integer
        number of points of the record.
    dtan : float
        time increment to be used in the analysis. If smaller than dtrec, OpenSeesPy interpolates.
    fact : float
        scale factor to apply to the record.
    damp : float
        Damping percentage in decimal (i.e., use 0.03 for 3%).
    IDctrlNode : int
        control node for the displacements.
    IDctrlDOF : int
        DOF for the displacement.
    elements : list
        elements to record forces and stresses.
    nodes_control : list
        nodes to compute displacements and inter-story drift. You must input one per floor, otherwise you'll get an error.
    modes : list, optional
        Modes of the structure to apply the Rayleigh damping. The default is [0,2] which uses the first and third mode.
    Kswitch : int, optional
        Use it to define which stiffness matrix should be used for the ramping. The default is 1 that uses initial stiffness. Input 2 for current stifness.
    Tol : float, optional
        Tolerance for the analysis. The default is 1e-4 because it uses the NormUnbalance test.

    Returns
    -------
    tiempo : numpy array
        Numpy array with analysis time.
    techo : numpy array
        Displacement of the control node.
    Eds :
        Numpy array with the forces in the elements (columns and beams). The order is determined by the order used in the input variable elements. The array has three dimensions. The first one is the element, the second one the pushover instant and the third one is the DOF.
    node_disp : numpy array
        Displacement at each node in nodes_control. Each column correspond to a node and each row to an analysis instant.
    node_vel : numpy array
        Velocity at each node in nodes_control. Each column correspond to a node and each row to an analysis instant.
    node_acel : numpy array
        Relative displacement at each node in nodes_control. Each column correspond to a node and each row to an analysis instant.
    drift : numpy array
        Drift at story of the building. Each column correspond to a node and each row to an analysis instant.
    Eds :
        Numpy array with the forces in the elements (columns and beams). The order is determined by the order used in the input variable elements. The array has three dimensions. The first one is the element, the second one the pushover instant and the third one is the DOF.
       
    residual_drift : numpy array  
        Residual drift at each story of the building, extracted from the last 2 seconds of free vibration. 
        
    node_acel_abs : numpy array  
        Absolute acceleration at each node in nodes_control. 
        

    '''
    # PARA SER UTILIZADO PARA CORRER EN PARALELO LOS SISMOS Y EXTRAYENDO LAS FUERZAS DE LOS ELEMENTOS INDICADOS EN ELEMENTS
    
    # record es el nombre del registro, incluyendo extensión. P.ej. GM01.txt
    # dtrec es el dt del registro
    # nPts es el número de puntos del análisis
    # dtan es el dt del análisis
    # fact es el factor escalar del registro
    # damp es el porcentaje de amortiguamiento (EN DECIMAL. p.ej: 0.03 para 3%)
    # IDcrtlNode es el nodo de control para grabar desplazamientos
    # IDctrlDOF es el grado de libertad de control
    # elements son los elementos de los que se va a grabar información
    # nodes_control son los nodos donde se va a grabar las respuestas
    # Kswitch recibe: 1: matriz inicial, 2: matriz actual
    
    maxNumIter = 10
    
    # creación del pattern
    
    timeSeries('Path',1000,'-filePath',recordName,'-dt',dtrec,'-factor',fact)
    pattern('UniformExcitation',  1000,   1,  '-accel', 1000)
    
    # damping
    nmodes = max(modes)+1
    eigval = eigen(nmodes)
    
    eig1 = eigval[modes[0]]
    eig2 = eigval[modes[1]]
    
    w1 = eig1**0.5
    w2 = eig2**0.5
    
    beta = 2.0*damp/(w1 + w2)
    alfa = 2.0*damp*w1*w2/(w1 + w2)
    
    if Kswitch == 1:
        rayleigh(alfa, 0.0, beta, 0.0)
    else:
        rayleigh(alfa, beta, 0.0, 0.0)
    
    # configuración básica del análisis
    wipeAnalysis()
    constraints('Plain')
    numberer('RCM')
    system('BandGeneral')
    test('NormUnbalance', Tol, maxNumIter)
    algorithm('Newton')    
    integrator('Newmark', 0.5, 0.25)
    analysis('Transient')
    
    # Otras opciones de análisis    
    tests = {1:'NormDispIncr', 2: 'RelativeEnergyIncr', 4: 'RelativeNormUnbalance',5: 'RelativeNormDispIncr', 6: 'NormUnbalance'}
    algoritmo = {1:'KrylovNewton', 2: 'SecantNewton' , 4: 'RaphsonNewton',5: 'PeriodicNewton', 6: 'BFGS', 7: 'Broyden', 8: 'NewtonLineSearch'}

    # rutina del análisis
    Nsteps_extra = int(2.0 / dtan)    #Numero de pasos extra para deriva residual (2 segundos)
    Nsteps =  int(dtrec*nPts/dtan)+Nsteps_extra
    dtecho = [nodeDisp(IDctrlNode,IDctrlDOF)]
    t = [getTime()]
    nels = len(elements)
    nnodos = len(nodes_control)
    Eds = np.zeros((nels, Nsteps+1, 6)) # para grabar las fuerzas de los elementos
    Prot = np.zeros((nels, Nsteps+1, 3)) # para grabar las rotaciones de los elementos
    
    
    node_disp = np.zeros((Nsteps + 1, nnodos)) # para grabar los desplazamientos de los nodos
    node_vel = np.zeros((Nsteps + 1, nnodos)) # para grabar los desplazamientos de los nodos
    node_acel = np.zeros((Nsteps + 1, nnodos)) # para grabar los desplazamientos de los nodos
    drift = np.zeros((Nsteps + 1, nnodos - 1)) # para grabar la deriva de entrepiso
    residual_drift = np.zeros(( 1, nnodos - 1)) # para grabar la deriva residual de entrepiso
    node_acel_abs = np.zeros((Nsteps + 1, nnodos)) # para grabar las aceleraciones absolutas de los nodos
    accg = np.zeros((Nsteps + 1, nnodos))  #para grabar las aceleraciones del suelo
    
    
    acc = np.loadtxt(recordName)  #Carga las aceleraciones de cada registro
       
    if len(acc) < Nsteps:
        acc = np.pad(acc, (0, Nsteps - len(acc)), mode='constant') #Llena de ceross el registro hasta los 2 segundos adicioanles del residual
    
    for k in range(Nsteps):
        ok = analyze(1,dtan)
        # ok2 = ok;
        # En caso de no converger en un paso entra al condicional que sigue
        if ok != 0:
            print('configuración por defecto no converge en tiempo: ',getTime())
            for j in algoritmo:
                if j < 4:
                    algorithm(algoritmo[j], '-initial')
    
                else:
                    algorithm(algoritmo[j])
                
                # el test se hace 50 veces más
                test('NormUnbalance', Tol, maxNumIter*50)
                ok = analyze(1,dtan)
                if ok == 0:
                    # si converge vuelve a las opciones iniciales de análisi
                    test('NormUnbalance', Tol, maxNumIter)
                    algorithm('Newton')
                    break
                    
        if ok != 0:
            print('Análisis dinámico fallido')
            print('Desplazamiento alcanzado: ',nodeDisp(IDctrlNode,IDctrlDOF),'m')
            break
        
        for node_i, node_tag in enumerate(nodes_control):
            
            node_disp[k+1,node_i] = nodeDisp(node_tag,1)
            node_vel[k+1,node_i] = nodeVel(node_tag,1)
            node_acel[k+1,node_i] = nodeAccel(node_tag,1)
            accg[k+1,node_i]= acc[k] * fact
            
                        
            if node_i != 0:
                drift[k+1,node_i-1] = (nodeDisp(node_tag,1) - nodeDisp(nodes_control[node_i-1],1))/(nodeCoord(node_tag,2) - nodeCoord(nodes_control[node_i-1],2))
        
        

        for el_i, ele_tag in enumerate(elements):
                      
            Eds[el_i , k+1, :] = [eleResponse(ele_tag,'globalForce')[0],
                                 eleResponse(ele_tag,'globalForce')[1],
                                 eleResponse(ele_tag,'globalForce')[2],
                                 eleResponse(ele_tag,'globalForce')[3],
                                 eleResponse(ele_tag,'globalForce')[4],
                                 eleResponse(ele_tag,'globalForce')[5]]

            Prot[el_i , k+1, :] = [eleResponse(ele_tag,'plasticDeformation')[0],
                                   eleResponse(ele_tag,'plasticDeformation')[1],
                                   eleResponse(ele_tag,'plasticDeformation')[2]]
            
            
            
        dtecho.append(nodeDisp(IDctrlNode,IDctrlDOF))
        t.append(getTime())
        
    # plt.figure()
    # plt.plot(t,dtecho)
    # plt.xlabel('tiempo (s)')
    # plt.ylabel('desplazamiento (m)')
    
    techo = np.array(dtecho)
    tiempo = np.array(t)
    
    for node_i, node_tag in enumerate(nodes_control):
        residual_drift[0,node_i-1]=ut.residual_disp(drift[:,node_i-1], Nsteps-Nsteps_extra)  #Se calcula deriva residual usando la funcion de Utilidades
    
    node_acel_abs= node_acel +  accg   #Calcula la aceleracion absoluta como la suma de la relativa y la del suelo
    
    wipe()
    return tiempo,techo,Eds,node_disp,node_vel,node_acel,drift,residual_drift,node_acel_abs,Prot

def spectrum4I(GM,dt,uy,xi=0.05,rango=[0.02,3.0],N=300):
    '''
    Calculates the Sa spectrum for a record using OpenSees sdfResponse

    Parameters
    ----------
    GM : string
        Name of the .txt file with the record (e.g. GM01.txt). One point per line.
    dt : float
        time increment of the record.
    xi : float, optional
        percent of critical damping as float (i.e. use 0.05 for 5%). The default is 0.05.
    rango : list, optional
        range of periods to calculate the spectrum. The default is [0.02,3.0].
    N : integer, optional
        number of periods to compute in the period range. The default is 300.

    Returns
    -------
    T : array
        periods.
    Sa : array
        spectral pseudo-acceleration for each period in T.
    U : array
        spectral displacement for each period in T.
    A : array
        acceleration for each period in T.

    '''
    
    m = 1
    T = np.linspace(rango[0],rango[1],N)
    w = 2*np.pi/T
    k = m*w**2
    fy = k*uy
    
    Sa = np.zeros(N)
    U = np.zeros(N)
    A = np.zeros(N)
    
    for indx, frec in enumerate(w):
        umax,ufin,uperm,amax,tamax = sdfResponse(m,xi,k[indx],fy[indx],0.0,dt,GM,dt)
        U[indx] = umax
        Sa[indx] = umax*frec**2
        A[indx] = amax
    return T,Sa,U,A

def dinamicoIDASDOF(recordName,dtrec,nPts,dtan,fact,damp,IDctrlNode,IDctrlDOF,wn,modes = [0,2],Kswitch = 1,Tol=1e-8):
    '''  
    Performs a dynamic analysis recording the displacement of a user selected node.
    Parameters
    ----------
    recordName : string
        Name of the record including file extension (i.e., 'GM01.txt'). It must have one record instant per line. 
    dtrec : float
        time increment of the record.
    nPts : integer
        number of points of the record.
    dtan : float
        time increment to be used in the analysis. If smaller than dtrec, OpenSeesPy interpolates.
    fact : float
        scale factor to apply to the record.
    damp : float
        Damping percentage in decimal (i.e., use 0.03 for 3%).
    IDctrlNode : int
        control node for the displacements.
    IDctrlDOF : int
        DOF for the displacement.
    modes : list, optional
        Modes of the structure to apply the Rayleigh damping. The default is [0,2] which uses the first and third mode.
    Kswitch : int, optional
        Use it to define which stiffness matrix should be used for the ramping. The default is 1 that uses initial stiffness. Input 2 for current stifness.
    Tol : float, optional
        Tolerance for the analysis. The default is 1e-4 because it uses the NormUnbalance test.

    Returns
    -------
    tiempo : numpy array
        Numpy array with analysis time.
    techo : numpy array
        Displacement of the control node.

    '''
    # PARA SER UTILIZADO PARA CORRER EN PARALELO LOS SISMOS
    
    # record es el nombre del registro, incluyendo extensión. P.ej. GM01.txt
    # dtrec es el dt del registro
    # nPts es el número de puntos del análisis
    # dtan es el dt del análisis
    # fact es el factor escalar del registro
    # damp es el porcentaje de amortiguamiento (EN DECIMAL. p.ej: 0.03 para 3%)
    # Kswitch recibe: 1: matriz inicial, 2: matriz actual
    
    maxNumIter = 10
    
    # creación del pattern
    
    timeSeries('Path',1000,'-filePath',recordName,'-dt',dtrec,'-factor',fact)
    pattern('UniformExcitation',  1000,   1,  '-accel', 1000)
    
    # damping
    beta = 2.0*damp/(wn + 1.3*wn)
    alfa = 2.0*damp*wn

    if Kswitch == 1:
        rayleigh(alfa, 0.0, 0.0, 0.0)
    else:
        rayleigh(alfa, beta, 0.0, 0.0)
    
    # configuración básica del análisis
    wipeAnalysis()
    constraints('Plain')
    numberer('RCM')
    system('BandGeneral')
    test('EnergyIncr', Tol, maxNumIter)
    algorithm('Newton')    
    integrator('Newmark', 0.5, 0.25)
    analysis('Transient')
    
    # Otras opciones de análisis    
    tests = {1:'NormDispIncr', 2: 'RelativeEnergyIncr', 4: 'RelativeNormUnbalance',5: 'RelativeNormDispIncr', 6: 'NormUnbalance'}
    algoritmo = {1:'KrylovNewton', 2: 'SecantNewton' , 4: 'RaphsonNewton',5: 'PeriodicNewton', 6: 'BFGS', 7: 'Broyden', 8: 'NewtonLineSearch'}

    # rutina del análisis
    
    Nsteps =  int(dtrec*nPts/dtan)
    dtecho = [nodeDisp(IDctrlNode,IDctrlDOF)]
    t = [getTime()]
    acel = []
    for k in range(Nsteps):
        ok = analyze(1,dtan)
        # ok2 = ok;
        # En caso de no converger en un paso entra al condicional que sigue
        if ok != 0:
            print('configuración por defecto no converge en tiempo: ',getTime())
            for j in algoritmo:
                if j < 4:
                    algorithm(algoritmo[j], '-initial')
    
                else:
                    algorithm(algoritmo[j])
                
                # el test se hace 50 veces más
                test('EnergyIncr', Tol, maxNumIter*50)
                ok = analyze(1,dtan)
                if ok == 0:
                    # si converge vuelve a las opciones iniciales de análisi
                    test('EnergyIncr', Tol, maxNumIter)
                    algorithm('Newton')
                    break
                    
        if ok != 0:
            print('Análisis dinámico fallido')
            print('Desplazamiento alcanzado: ',nodeDisp(IDctrlNode,IDctrlDOF),'m')
            break
    
        
        dtecho.append(nodeDisp(IDctrlNode,IDctrlDOF))
        t.append(getTime())
        acel.append(nodeAccel(IDctrlNode,IDctrlDOF))
        
    # plt.figure()
    # plt.plot(t,dtecho)
    # plt.xlabel('tiempo (s)')
    # plt.ylabel('desplazamiento (m)')
    
    techo = np.array(dtecho)
    tiempo = np.array(t)
    acel = np.array(acel)
    wipe()
    return tiempo,techo,acel

def spectrum5(GM,dt,xi=0.05,rango=[0.02,3.0],N=300):
    
    m = 1
    T = np.linspace(rango[0],rango[1],N)
    w = 2*np.pi/T
    k = m*w**2
    GM_input = np.loadtxt(GM)
    npoints = len(GM_input)
    print(npoints)
    Sa = np.zeros(N)
    U = np.zeros(N)
    A = np.zeros(N)
    
    for indx, frec in enumerate(w):
        wipe()
        model('basic','-ndm',2,'-ndf',3)
        
        node(1,0.0,0.0)
        node(2,0.0,0.0)
        
        fix(1, 1, 1, 1)
        fix(2, 0, 1, 1)
        
        mass(2,m,m)
        
        matTag = 1
        uniaxialMaterial('Elastic', 1, k[indx])
        
        controlnode = 2
        element('zeroLength',1,1,2,'-mat',matTag,'-dir',1)
        
        t, d, acel = dinamicoIDASDOF(GM, dt, npoints, dt, 1, xi, 2, 1, frec)
        U[indx] = np.max(np.abs(d))
        Sa[indx] = w[indx]**2*np.max(np.abs(d))
        n = min(len(acel), len(GM_input))
        acel_abs = acel[:n] + GM_input[:n]
        A[indx] = np.max(np.abs(acel_abs))
        
    return T,Sa,U,A

def get_diagonal_node_pairs(coordx,coordy):
    '''
    Function to get a floor-wise list with the possible pairs of nodes to define diagonals.
    
    Parameters
    ----------
    coordx : list
        List with the X coordinates.
    coordy : list
        List with the Y coordinates.

    Returns
    -------
    diagonal_pairs : list
        returns a floor-wise and span-wise list with the possible pairs of nodes to define diagonals.
    diagonal_length: list
        returns a floor-wise and span-wise length of the diagonals
    
    '''
    
    ny = len(coordy)
    nx = len(coordx)
    diagonal_pairs = []
    diagonal_length = []
    for j in range(ny-1):
        floor_pairs = []
        floor_length = []
        for i in range(nx-1):
            nnode1 = 1000*(i+1)+j
            nnode2 = 1000*(i+2)+j+1
            nnode3 = 1000*(i+1)+j+1
            nnode4 = 1000*(i+2)+j
            floor_pairs.append([nnode1, nnode2, nnode4, nnode3])
            a1 = np.array(nodeCoord(nnode1))
            a2 = np.array(nodeCoord(nnode2))
            floor_length.append(np.linalg.norm(a2-a1))
            
        diagonal_pairs.append(floor_pairs)
        diagonal_length.append(floor_length)
    return diagonal_pairs, diagonal_length


def assign_infills(diagonal_pairs,building_infill_areas,building_infill_materials):
    '''
    Function to assign infills to the building
    Parameters
    ----------
    diagonal_pairs : list
        list containing floor-wise and span-wise node coordinates of the nodes.
    building_infill_areas : list
        list containing floor-wise and span-wise the areas of the infills.
    building_infill_materials : list
        list containing floor-wise and span-wise the materials of the infills.

    Returns
    -------
    None.

    '''
    nfloors = len(diagonal_pairs)
    for i in range(nfloors):
        floor_diagonals = diagonal_pairs[i]
        floor_infill_areas = building_infill_areas[i]
        floor_infill_materials = building_infill_materials[i]
        for j,mat in enumerate(floor_infill_materials):
            if mat != 'None':
                eltag1 = -1000*(i+1) - 10*j
                eltag2 = -1000*(i+1) - 10*j - 1
                nodes = floor_diagonals[j]
                element('Truss',eltag1,nodes[0],nodes[1],floor_infill_areas[j],
                        mat)
                element('Truss',eltag2,nodes[2],nodes[3],floor_infill_areas[j],
                        mat)
                #element('Truss',eltag,nodeBtm,nodeTop,A[i,j],MasonryD)
    
def col_infill(fm,mat_tag,brick_type = 'VP'):
    '''
    Function to generate the infill material. Uses Guerrero et al. (2022) for horizontal perforation bricks and Borah et al. (2021) for horizontal perforation

    Parameters
    ----------
    fm : float
        brick fm in MPa.
    mat_tag : integer
        tag of the material.
    brick_type : string, optional
        VP for vertical perforation, HP for horizontal perforation. The default is 'VP'.

    Returns
    -------
    None.

    '''
    if brick_type == 'VP':
        Em = 775*fm
    elif brick_type == 'HP':
        Em = 622*fm
    fmu = 0.05*fm
    e0 = 2*fm/Em
    emu = 2*e0
    uniaxialMaterial('Concrete01',mat_tag, fm*1000, e0, fmu*1000, emu) # Se multiplica por 1000 para pasar a kN que son las unidades del modelo

def infill_widths(diagonal_lengths,width_percentage):
    np_array = np.array(diagonal_lengths)
    biw = np_array*width_percentage
    building_infill_widths = biw.tolist()
    return building_infill_widths