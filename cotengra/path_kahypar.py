import random
import itertools
from os.path import join, abspath, dirname

from .core import PartitionTreeBuilder, get_hypergraph
from .hyper import register_hyper_function

# needed to supply kahypar profile files
KAHYPAR_PROFILE_DIR = join(abspath(dirname(__file__)), 'kahypar_profiles')


def to_sparse(hg, weight_nodes='const', weight_edges='log'):
    winfo = hg.compute_weights(weight_nodes=weight_nodes,
                               weight_edges=weight_edges)

    hyperedge_indices = []
    hyperedges = []
    for e in winfo['edge_list']:
        hyperedge_indices.append(len(hyperedges))
        hyperedges.extend(hg.edges[e])
    hyperedge_indices.append(len(hyperedges))

    winfo['hyperedge_indices'] = hyperedge_indices
    winfo['hyperedges'] = hyperedges
    return winfo


def kahypar_subgraph_find_membership(
    inputs,
    output,
    size_dict,
    weight_nodes='const',
    weight_edges='log',
    fix_output_nodes=False,
    parts=2,
    imbalance=0.01,
    compress=0,
    seed=None,
    profile=None,
    mode='direct',
    objective='cut',
    quiet=True,
    use_cyc = None
):
    import kahypar as kahypar

    if seed is None:
        seed = random.randint(0, 2**31 - 1)

    nv = len(inputs)
    if parts >= nv:
        return list(range(nv))

    #cyc added use_cyc
    hg = get_hypergraph(inputs, output, size_dict, accel=False, use_cyc=use_cyc)

    if compress:
        hg.compress(compress)

    winfo = to_sparse(hg, weight_nodes=weight_nodes, weight_edges=weight_edges)

    hypergraph_kwargs = {
        'num_nodes': hg.get_num_nodes(),
        'num_edges': hg.get_num_edges(),
        'index_vector': winfo['hyperedge_indices'],
        'edge_vector': winfo['hyperedges'],
        'k': parts,
    }

    edge_weights, node_weights = {
        (False, False): (None, None),
        (False, True): ([], winfo['node_weights']),
        (True, False): (winfo['edge_weights'], []),
        (True, True): (winfo['edge_weights'], winfo['node_weights']),
    }[winfo['has_edge_weights'], winfo['has_node_weights']]

    if edge_weights or node_weights:
        hypergraph_kwargs['edge_weights'] = edge_weights
        hypergraph_kwargs['node_weights'] = node_weights

    hypergraph = kahypar.Hypergraph(**hypergraph_kwargs)

    if fix_output_nodes:
        # make sure all the output nodes (those with output indices) are in
        # the same partition
        onodes = tuple(hg.output_nodes())

        if parts >= nv - len(onodes) + 1:
            # too many partitions, simply group all outputs and return
            groups = itertools.count(1)
            return [0 if i in onodes else next(groups) for i in range(nv)]

        for i in onodes:
            hypergraph.fixNodeToBlock(i, 0)

        # silences various warnings
        mode = 'recursive'

    if profile is None:
        profile_mode = {'direct': 'k', 'recursive': 'r'}[mode]
        profile = f"{objective}_{profile_mode}KaHyPar_sea20.ini"

    context = kahypar.Context()
    context.loadINIconfiguration(join(KAHYPAR_PROFILE_DIR, profile))
    context.setK(parts)
    context.setSeed(seed)
    context.suppressOutput(quiet)
    context.setEpsilon(imbalance * parts)

    kahypar.partition(hypergraph, context)

    if use_cyc == 1:
        return [hypergraph.blockID(i) for i in hypergraph.nodes()][:hg.origin_num_nodes]# cyc added

    return [hypergraph.blockID(i) for i in hypergraph.nodes()]


kahypar_to_tree = PartitionTreeBuilder(kahypar_subgraph_find_membership)

register_hyper_function(
    name='kahypar',
    ssa_func=kahypar_to_tree.trial_fn,
    space={
        'random_strength': {'type': 'FLOAT_EXP', 'min': 0.01, 'max': 10.},
        'weight_edges': {'type': 'STRING', 'options': ['const', 'log']},
        'cutoff': {'type': 'INT', 'min': 10, 'max': 40},
        'imbalance': {'type': 'FLOAT', 'min': 0.01, 'max': 1.0},
        'imbalance_decay': {'type': 'FLOAT', 'min': -5, 'max': 5},
        'parts': {'type': 'INT', 'min': 2, 'max': 16},
        'parts_decay': {'type': 'FLOAT', 'min': 0.0, 'max': 1.0},
        'mode': {'type': 'STRING', 'options': ['direct', 'recursive']},
        'objective': {'type': 'STRING', 'options': ['cut', 'km1']},
        'fix_output_nodes': {'type': 'STRING', 'options': ['auto', '']},
    },
)

register_hyper_function(
    name='kahypar-balanced',
    ssa_func=kahypar_to_tree.trial_fn,
    space={
        'weight_edges': {'type': 'STRING', 'options': ['const', 'log']},
        'cutoff': {'type': 'INT', 'min': 2, 'max': 4},
        'imbalance': {'type': 'FLOAT', 'min': 0.001, 'max': 0.01},
        'mode': {'type': 'STRING', 'options': ['direct', 'recursive']},
        'objective': {'type': 'STRING', 'options': ['cut', 'km1']},
        'fix_output_nodes': {'type': 'STRING', 'options': ['auto', '']},
    },
    constants={
        'random_strength': 0.0,
        'imbalance_decay': 0.0,
        'parts': 2,
    }
)


register_hyper_function(
    name='kahypar-agglom',
    ssa_func=kahypar_to_tree.trial_fn_agglom,
    space={
        'weight_edges': {'type': 'STRING', 'options': ['const', 'log']},
        'imbalance': {'type': 'FLOAT', 'min': 0.001, 'max': 0.05},
        'mode': {'type': 'STRING', 'options': ['direct', 'recursive']},
        'objective': {'type': 'STRING', 'options': ['cut', 'km1']},
        'groupsize': {'type': 'INT', 'min': 2, 'max': 10},
        'fix_output_nodes': {'type': 'STRING', 'options': ['auto', '']},
        'compress': {'type': 'STRING', 'options': [0, 3, 10, 30, 100]}
    },
    constants={
        'random_strength': 0.0,
    }
)



#cyc added

register_hyper_function(
    name='cyc_kahypar',
    ssa_func=kahypar_to_tree.trial_fn,
    space={
        'random_strength': {'type': 'FLOAT_EXP', 'min': 0.01, 'max': 10.},
        'weight_edges': {'type': 'STRING', 'options': ['const', 'log']},
        'cutoff': {'type': 'INT', 'min': 10, 'max': 40},
        'imbalance': {'type': 'FLOAT', 'min': 0.01, 'max': 1.0},
        'imbalance_decay': {'type': 'FLOAT', 'min': -5, 'max': 5},
        'parts': {'type': 'INT', 'min': 2, 'max': 16},
        'parts_decay': {'type': 'FLOAT', 'min': 0.0, 'max': 1.0},
        'mode': {'type': 'STRING', 'options': ['direct', 'recursive']},
        'objective': {'type': 'STRING', 'options': ['cut', 'km1']},
    },
    constants={
    'use_cyc': 1,
    }

)

register_hyper_function(
    name='cyc_kahypar-balanced',
    ssa_func=kahypar_to_tree.trial_fn,
    space={
        'weight_edges': {'type': 'STRING', 'options': ['const', 'log']},
        'cutoff': {'type': 'INT', 'min': 2, 'max': 4},
        'imbalance': {'type': 'FLOAT', 'min': 0.001, 'max': 0.01},
        'mode': {'type': 'STRING', 'options': ['direct', 'recursive']},
        'objective': {'type': 'STRING', 'options': ['cut', 'km1']},
    },
    constants={
        'random_strength': 0.0,
        'imbalance_decay': 0.0,
        'parts': 2,
        'use_cyc': 1,
    }
)


register_hyper_function(
    name='cyc_kahypar-agglom',
    ssa_func=kahypar_to_tree.trial_fn_agglom,
    space={
        'weight_edges': {'type': 'STRING', 'options': ['const', 'log']},
        'imbalance': {'type': 'FLOAT', 'min': 0.001, 'max': 0.05},
        'mode': {'type': 'STRING', 'options': ['direct', 'recursive']},
        'objective': {'type': 'STRING', 'options': ['cut', 'km1']},
        'groupsize': {'type': 'INT', 'min': 2, 'max': 10},
        'compress': {'type': 'STRING', 'options': [0, 3, 10, 30, 100]}
    },
    constants={
        'random_strength': 0.0,
        'use_cyc': 1,
    }
)



#cyc added

register_hyper_function(
    name='cyc2_kahypar',
    ssa_func=kahypar_to_tree.trial_fn,
    space={
        'random_strength': {'type': 'FLOAT_EXP', 'min': 0.01, 'max': 10.},
        'weight_edges': {'type': 'STRING', 'options': ['const', 'log']},
        'cutoff': {'type': 'INT', 'min': 10, 'max': 40},
        'imbalance': {'type': 'FLOAT', 'min': 0.01, 'max': 1.0},
        'imbalance_decay': {'type': 'FLOAT', 'min': -5, 'max': 5},
        'parts': {'type': 'INT', 'min': 2, 'max': 16},
        'parts_decay': {'type': 'FLOAT', 'min': 0.0, 'max': 1.0},
        'mode': {'type': 'STRING', 'options': ['direct', 'recursive']},
        'objective': {'type': 'STRING', 'options': ['cut', 'km1']},
    },
    constants={
    'use_cyc': 2,
    }

)

register_hyper_function(
    name='cyc2_kahypar-balanced',
    ssa_func=kahypar_to_tree.trial_fn,
    space={
        'weight_edges': {'type': 'STRING', 'options': ['const', 'log']},
        'cutoff': {'type': 'INT', 'min': 2, 'max': 4},
        'imbalance': {'type': 'FLOAT', 'min': 0.001, 'max': 0.01},
        'mode': {'type': 'STRING', 'options': ['direct', 'recursive']},
        'objective': {'type': 'STRING', 'options': ['cut', 'km1']},
    },
    constants={
        'random_strength': 0.0,
        'imbalance_decay': 0.0,
        'parts': 2,
        'use_cyc': 2,
    }
)


register_hyper_function(
    name='cyc2_kahypar-agglom',
    ssa_func=kahypar_to_tree.trial_fn_agglom,
    space={
        'weight_edges': {'type': 'STRING', 'options': ['const', 'log']},
        'imbalance': {'type': 'FLOAT', 'min': 0.001, 'max': 0.05},
        'mode': {'type': 'STRING', 'options': ['direct', 'recursive']},
        'objective': {'type': 'STRING', 'options': ['cut', 'km1']},
        'groupsize': {'type': 'INT', 'min': 2, 'max': 10},
        'compress': {'type': 'STRING', 'options': [0, 3, 10, 30, 100]}
    },
    constants={
        'random_strength': 0.0,
        'use_cyc': 2,
    }
)
