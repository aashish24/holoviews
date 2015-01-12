from collections import OrderedDict

import numpy as np

import param

from ..core import Dimension, Layer, NdMapping, ViewMap


class ItemTable(Layer):
    """
    A tabular view type to allow convenient visualization of either a
    standard Python dictionary or an OrderedDict. If an OrderedDict is
    used, the headings will be kept in the correct order. Tables store
    heterogeneous data with different labels.

    Dimension objects are also accepted as keys, allowing dimensional
    information (e.g type and units) to be associated per heading.
    """

    xlabel, ylabel = None, None
    xlim, ylim = None, None
    lbrt = None, None, None, None

    @property
    def rows(self):
        return self.ndims


    @property
    def cols(self):
        return 2


    def __init__(self, data, **params):
        # Assume OrderedDict if not a vanilla Python dict
        if type(data) == dict:
            data = OrderedDict(sorted(data.items()))

        data=dict((k.name if isinstance(k, Dimension)
                   else k ,v) for (k,v) in data.items())
        super(ItemTable, self).__init__(data, dimensions=data.keys(), **params)


    def __getitem__(self, heading):
        """
        Get the value associated with the given heading (key).
        """
        if heading is ():
            return self
        if heading not in self.dim_dict:
            raise IndexError("%r not in available headings." % heading)
        if isinstance(heading, Dimension):
            return self.data[heading.name]
        else:
            return self.data[heading]


    def sample(self, samples=None):
        if callable(samples):
            sampled_data = OrderedDict(item for item in self.data.items()
                                       if samples(item))
        else:
            sampled_data = OrderedDict((s, self.data[s]) for s in samples)
        return self.clone(sampled_data)


    def reduce(self, **reduce_map):
        raise NotImplementedError('ItemTables are for heterogeneous data, which'
                                  'cannot be reduced.')


    def cell_value(self, row, col):
        """
        Get the stored value for a given row and column indices.
        """
        if col > 2:
            raise Exception("Only two columns available in a ItemTable.")
        elif row >= self.rows:
            raise Exception("Maximum row index is %d" % self.rows-1)
        elif col == 0:
            return list(self.dim_dict.values())[row]
        else:
            heading = list(self.dim_dict.keys())[row]
            return self.data[heading]


    def hist(self, *args, **kwargs):
        raise NotImplementedError("ItemTables are not homogenous and "
                                  "don't support histograms.")


    def cell_type(self, row, col):
        """
        Returns the cell type given a row and column index. The common
        basic cell types are 'data' and 'heading'.
        """
        if col == 0:  return 'heading'
        else:         return 'data'


    def dframe(self):
        """
        Generates a Pandas dframe from the ItemTable.
        """
        from pandas import DataFrame
        return DataFrame({(k.name if isinstance(k, Dimension)
                           else k): [v] for k, v in self.data.items()})



class Table(Layer, NdMapping):
    """
    A Table is an NdMapping that is rendered in tabular form. In
    addition to the usual multi-dimensional keys of NdMappings
    (rendered as columns), Tables also support multi-dimensional
    values also rendered as columns. The values held in a multi-valued
    Table are tuples, where each component of the tuple maps to a
    column as described by the value_dimensions parameter.

    In other words, the columns of a table are partitioned into two
    groups: the columns based on the key and the value columns that
    contain the components of the value tuple.

    One feature of Tables is that they support an additional level of
    index over NdMappings: the last index may be a column name or a
    slice over the column names (using alphanumeric ordering).
    """

    value = param.ClassSelector(class_=Dimension,
                                default=Dimension(name='Table'),  doc="""
         The value Dimension is used to describe the table. Example of
         dimension names include 'Summary' or 'Statistics'. """)

    value_dimensions = param.List(default=[Dimension('Data')],
                                  bounds=(1,None), doc="""
        The dimension description(s) of the values held in data tuples
        that map to the value columns of the table.

        Note: String values may be supplied in the constructor which
        will then be promoted to Dimension objects.""")

    xlabel, ylabel = None, None
    xlim, ylim = None, None
    lbrt = None, None, None, None

    def __init__(self, data=None, **params):
        self._style = None
        NdMapping.__init__(self, data, **dict(params,
                                              value=params.get('value',self.value)))
        self.data = self._data # For multiple columns, values are tuples.
        value_dimensions = [v if isinstance(v, Dimension)
                            else Dimension(v) for v in self.value_dimensions]
        self.value_dimensions = value_dimensions


    def _filter_columns(self, index, col_names):
        "Returns the column names specified by index (which may be a slice)"
        if isinstance(index, slice):
            cols  = [col for col in sorted(col_names)]
            if index.start:
                cols = [col for col in cols if col > index.start]
            if index.stop:
                cols = [col for col in cols if col < index.stop]
            cols = cols[::index.step] if index.step else cols
        elif index not in col_names:
            raise KeyError("No column with dimension label %r" % index)
        else:
            cols= [index]
        if cols==[]:
            raise KeyError("No columns selected in the given slice")
        return cols


    def __getitem__(self, args):
        """
        In addition to usual NdMapping indexing, Tables can be indexed
        by column name (or a slice over column names)
        """
        ndmap_index = args[:self.ndims] if isinstance(args, tuple) else args
        subtable = NdMapping.__getitem__(self, ndmap_index)

        if not isinstance(subtable, Table):
            # If a value tuple, turn into an ItemTable
            subtable = ItemTable(OrderedDict(zip(self.value_dimensions, subtable)),
                                 label=self.label)

        if not isinstance(args, tuple) or len(args) <= self.ndims:
            return subtable

        col_names = [dim.name for dim in self.value_dimensions]
        cols = self._filter_columns(args[-1], col_names)
        indices = [col_names.index(col) for col in cols]
        value_dimensions=[self.value_dimensions[i] for i in indices]
        if isinstance(subtable, ItemTable):
            items = OrderedDict([(h,v) for (h,v) in subtable.data.items() if h in cols])
            return ItemTable(items, label=self.label)

        items = [(k, tuple(v[i] for i in indices)) for (k,v) in subtable.items()]
        return subtable.clone(items, value_dimensions=value_dimensions)


    @property
    def range(self):
        if isinstance(self.value, list) and len(self.value) != 1:
            raise Exception("Range only supported if there is a single value column")
        values = self.values()
        return (min(values), max(values))

    @property
    def rows(self):
        return len(self._data) + 1

    @property
    def cols(self):
        return self.ndims + max([len(self.value_dimensions),1])

    def clone(self, *args, **params):
        return NdMapping.clone(self, *args, **params)


    def cell_value(self, row, col):
        """
        Get the stored value for a given row and column indices.
        """
        if col >= self.cols:
            raise Exception("Maximum column index is %d" % self.cols-1)
        elif row >= self.rows:
            raise Exception("Maximum row index is %d" % self.rows-1)
        elif row == 0:
            if col >= self.ndims:
                return str(self.value_dimensions[col - self.ndims])
            return str(self.dimensions[col])
        else:
            if col >= self.ndims:
                row_values = self.values()[row-1]
                return (row_values[col - self.ndims]
                        if isinstance(row_values, tuple) else row_values)

            return self._data.keys()[row-1][col]
            heading = list(self.dim_dict.keys())[row]
            return self.data[heading]


    def cell_type(self, row, col):
        """
        Returns the cell type given a row and column index. The common
        basic cell types are 'data' and 'heading'.
        """
        return 'heading' if row == 0 else 'data'


    def sample(self, samples=[]):
        """
        Allows sampling of the Table with a list of samples.
        """
        sample_data = OrderedDict()
        for sample in samples:
            sample_data[sample] = self[sample]
        return Table(sample_data, **dict(self.get_param_values()))


    def reduce(self, **reduce_map):
        """
        Allows collapsing the Table down by dimension by passing
        the dimension name and reduce_fn as kwargs. Reduces
        dimensionality of Table until only an ItemTable is left.
        """
        dim_labels = self.dimension_labels
        reduced_table = self
        for dim, reduce_fn in reduce_map.items():
            split_dims = [self.dim_dict[d] for d in dim_labels if d != dim]
            if len(split_dims):
                split_map = reduced_table.split_dimensions([dim])
                reduced_table = self.clone(None, dimensions=split_dims)
                for k, table in split_map.items():
                    reduced_table[k] = reduce_fn(table.data.values())
            else:
                data = reduce_fn(reduced_table.data.values())
                reduced_table = ItemTable({self.value.name: data},
                                          dimensions=[self.value])
        return reduced_table


    def _item_check(self, dim_vals, data):
        if isinstance(data, tuple):
            for el in data:
                self._item_check(dim_vals, el)
            return
        if not np.isscalar(data):
            raise TypeError('Table only accepts scalar values.')
        super(Table, self)._item_check(dim_vals, data)


    def viewmap(self, dimensions):
        split_dims = [dim for dim in self.dimension_labels
                      if dim not in dimensions]
        if len(dimensions) < self.ndims:
            return self.split_dimensions(split_dims, map_type=ViewMap)
        else:
            vmap = ViewMap(dimensions=dimensions)
            for k, v in self.items():
                vmap[k] = ItemTable({self.value.name: v}, dimensions=[self.value])
            return vmap


    def dim_values(self, dim):
        if dim == self.value.name:
            return self.values()
        elif isinstance(self.value, list) and dim in self.value:
            index = [v.name for v in self.value].index(dim)
            return [v[index] for v in self.values()]
        else:
            return NdMapping.dim_values(self, dim)


    def dframe(self):
        return NdMapping.dframe(self, value_label=self.value.name)
