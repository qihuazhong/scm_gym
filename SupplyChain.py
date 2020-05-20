from dataclasses import dataclass, field
from typing import List




@dataclass
class Order:
    order_quantity: float
    shipped_quantity: float = 0.
    time_till_received: int = 0
        
    @property
    def unshipped_quantity(self):
        return self.order_quantity - self.shipped_quantity
    
    @property
    def requires_shipping(self):
        # requires a shipment if order is received and unshipped quantity is positive
        return (self.time_till_received == 0) and (self.shipped_quantity < self.order_quantity)


@dataclass
class Shipment:
    quantity: float
    time_till_arrival: int



class OrderList(list):
    
    @property
    def requires_shipment_subtotal(self):
        return sum([so.unshipped_quantity for so in self if so.time_till_received == 0])
    
    
    def clean_finished_orders(self):
        self.sort(key=lambda x: x.unshipped_quantity, reverse=True)
        while (self.__len__() > 0) and (self[-1].unshipped_quantity == 0):
            self.pop()
    
    

class ShipmentList(list):
    
    
    def receive_shipments(self):
        
        arrived_quantity = 0
        self.sort(key=lambda x: x.time_till_arrival, reverse=True) 
        while (self.__len__() > 0) and (self[-1].time_till_arrival <= 0):
            popped_shipment = self.pop()
            arrived_quantity += popped_shipment.quantity   
            
        return arrived_quantity
    
    
    @property
    def en_route_subtotal(self):
        return sum([sm.quantity for sm in self])
    
    
    
    
    
    
class Node():
    
    def __init__(self, name, policy=None, demand_source=False, demands=None, supply_source = False, initial_inventory=12, holding_cost=0.5, stockout_cost=1.0, initial_previous_orders=None):
        
        self.name = name
        self.demands = demands
        self.policy = policy
        
        self.demand_source = demand_source # 'demand node' with external demand
        self.supply_source = supply_source # 'supplier node' with unlimited supply
        
        self.unit_holding_cost = holding_cost
        self.unit_stockout_cost = stockout_cost
        
        self.initial_inventory =  9999999 if supply_source else initial_inventory
        self.initial_previous_orders = initial_previous_orders
        
        self.reset()
        
        

    def __str__(self):
        return 'Node({}: Inventory: {}, Unfilled Demand: {})'.format(self.name, self.current_inventory, self.unfilled_demand)
    
    def __repr__(self):
        return self.__str__()
    
    
        
    def reset(self):
        self.current_inventory = self.initial_inventory
        self.previous_orders = [] if self.initial_previous_orders is None else self.initial_previous_orders[:]
            
        
        self.unfilled_demand = 0
        
        self.current_stockout_cost = 0
        self.current_holding_cost = 0
        
        self.latest_demand = []
        
        self.stockout_cost_history = []
        self.holding_cost_history = []
        self.order_history = []
        
        if self.demand_source:
            self.demands.reset()

    
    def place_order(self, states, arc, period, order_quantity=None):
        
        
        if self.demand_source:
            order_quantity = self.demands.get_demand(period)
            new_order = Order(order_quantity, 0, arc.information_leadtime)
            arc.sales_orders.append(new_order)
            
        else:
        
            if order_quantity is None:
                order_quantity = self.policy.get_order_quantity(states)

                

                
            # track order hisotry for reporting states
            self.previous_orders.pop()
            self.previous_orders.insert(0, order_quantity)
            
            new_order = Order(order_quantity, 0, arc.information_leadtime)
            
            
#             if self.name == 'wholesaler':
#                 print('placing order for wholeslaer:')
#                 print(states)
#                 print(new_order)
            arc.sales_orders.append(new_order)
            
        self.order_history.append(order_quantity)
        

        
        
class Arc():
    
    def __init__(self, source, target, information_leadtime, shipment_leadtime, initial_shipments=None, initial_SOs=None):
        self.source = source
        self.target = target
        self.information_leadtime = information_leadtime
        
        self.shipment_leadtime = shipment_leadtime
        self.initial_shipments = initial_shipments
        self.initial_SOs = initial_SOs
        
        self.reset()
        
    def reset(self):
        self.shipments = ShipmentList([] if self.initial_shipments is None else [Shipment(s[0], s[1]) for s in self.initial_shipments])
        self.sales_orders = OrderList([] if self.initial_SOs is None else [Order(s[0], 0, s[2]) for s in self.initial_SOs])
        
        
    def advance_order_slips(self):
        
        latest_demand = 0
        for so in self.sales_orders:
            if  so.time_till_received > 0:
                if so.time_till_received == 1:
                    latest_demand += so.order_quantity
                so.time_till_received -= 1
        return latest_demand
    
    
    def advance_shipments(self):
          
        # advance shipments        
        for shipment in self.shipments:
            shipment.time_till_arrival -= 1
    
        arrived_quantity = self.shipments.receive_shipments()
        
        return arrived_quantity
    
    
                    
    def fill_orders(self, node):
        
        unfilled_quantity = 0

        for so in self.sales_orders: 
            if so.requires_shipping:

                # quantity of the new shipment should be minimum between available invenotry and unshipped quantity
                quantity = min(node.current_inventory, so.unshipped_quantity)
                if quantity > 0:
                    self.shipments.append(Shipment(quantity, self.shipment_leadtime))
                    so.shipped_quantity += quantity

                if node.supply_source == False:
                    node.current_inventory -= quantity
                
                unfilled_quantity += (so.unshipped_quantity)
                
        # clean up finished orders
        self.sales_orders.clean_finished_orders()
            
        return unfilled_quantity
                    
                    
    def __str__(self):
        return 'arc(source:{}, target:{}, information leadtime:{}, shipment leadtime:{})'.format(self.source, self.target, self.information_leadtime,self.shipment_leadtime)
    
    
    def __repr__(self):
        return self.__str__()
    
    
    
    
    
class Supply_chain_network():

    '''
    order of operations: receive shipments from supplier 
                            -> ship products to customer 
                            -> receive new sales orders
    '''
    def __init__(self, nodes, arcs, player):
        self.nodes = {node.name: node for node in nodes}
        self.arcs = {(arc.source, arc.target): arc for arc in arcs}
        
        self.demand_sources = [node.name for node in nodes if node.demand_source]
        self.supply_sources = [node.name for node in nodes if node.supply_source]
        
        self.suppliers = {node.name: [arc.source for arc in arcs if arc.target == node.name] for node in nodes}
        self.customers = {node.name: [arc.target for arc in arcs if arc.source == node.name] for node in nodes}

        self.shipment_sequence = self._parse_shipment_sequence()
        self.order_sequence = self._parse_order_sequence()
        
        self.player = player
        self.player_index = self.order_sequence.index(player)

    
    def __str__(self):
        string = ''
        for arc in self.arcs:
            string += '{} -> {} \n'.format(self.arcs[arc].source, self.arcs[arc].target) 
        return string
    
    
    def __repr__(self):
        return self.__str__()
    
    
    def summary(self):
        
        for node in self.shipment_sequence:
            print('Node: {}'.format(node))
            print('\tInventory: {}'.format(self.nodes[node].current_inventory))
            print('\tUnfilled Demand: {}'.format(self.nodes[node].unfilled_demand))
            print('\tCurrent Stockout Cost: {}'.format(self.nodes[node].current_stockout_cost))
            print('\tCurrent Holding Cost: {}'.format(self.nodes[node].current_holding_cost))
        
        for arc in self.arcs.keys():
            print('{} -> {}'.format(self.arcs[arc].source, self.arcs[arc].target))
            
            print('\tOrders')
            for so in self.arcs[arc].sales_orders:
                print('\t {}'.format(so))
                
            print('\tShipments')
            for shipment in self.arcs[arc].shipments:
                print('\t {}'.format(shipment))
                
                
    def reset(self):
        for node in self.nodes:
            self.nodes[node].reset()
            
        for arc in self.arcs:
            self.arcs[arc].reset()
            
    
    def _parse_shipment_sequence(self):
        
        shipped = []
        not_shipped = [node for node in self.nodes]
        while len(not_shipped) > 0:
            for node in not_shipped:
                ready = True
                for supplier in self.suppliers[node]:
                    if supplier not in shipped:
                        ready = False
                if ready:
                    not_shipped.remove(node)
                    shipped.append(node)

        return shipped 
            
        
    def _parse_order_sequence(self):
        
        ordered = []
        not_ordered = [node for node in self.nodes]
        while len(not_ordered) > 0:
            for node in not_ordered:
                ready= True
                for customer in self.customers[node]:
                    if customer not in ordered:
                        ready = False
                if ready:
                    not_ordered.remove(node)
                    ordered.append(node)
                
        return ordered
    
    
    def get_states(self, node, period):
        
        # Inventory
        inventory = self.nodes[node].current_inventory
        
        # unfilled demand
        if node in self.demand_sources:
            unfilled_demand = self.nodes[node].demands.get_demand(period)
        else:
            customers = self.customers[node]
            downstream_arcs = [self.arcs[(node, customer)] for customer in customers]
            
            unfilled_demand = [arc.sales_orders.requires_shipment_subtotal for arc in downstream_arcs]
            unfilled_demand = sum(unfilled_demand)

            
        # latest demand
        latest_demand = sum(self.nodes[node].latest_demand)

        # on order quantity
        suppliers = self.suppliers[node]
        upstream_arcs = [self.arcs[(supplier, node)] for supplier in suppliers]
        
        unshipped = sum([so.unshipped_quantity for arc in upstream_arcs for so in arc.sales_orders])
        en_route = sum([arc.shipments.en_route_subtotal for arc in upstream_arcs])
        on_order = unshipped + en_route
        
        
        states_dict = {'inventory':inventory, 'unfilled_demand':unfilled_demand, 'latest_demand':latest_demand, 'on_order':on_order}
        
        previous_orders_dict = {'previous_order_{}'.format(i) : self.nodes[node].previous_orders[i] 
                                for i in range(len(self.nodes[node].previous_orders))}

        return {**states_dict, **previous_orders_dict}

            
            
    def before_action(self, period):
        
         
        for node in self.order_sequence:
            self.nodes[node].latest_demand = []
            
        # advance order slips       
        for node in self.order_sequence:
            for supplier in self.suppliers[node]:
                latest_demand = self.arcs[(supplier, node)].advance_order_slips()
                self.nodes[supplier].latest_demand.append(latest_demand)

    
        # advance shipments    
        for node in self.shipment_sequence:
            for customer in self.customers[node]:    
                # Increase customer's inventory when the shipments arrive
                arrived_quantity = self.arcs[(node, customer)].advance_shipments()
                self.nodes[customer].current_inventory += arrived_quantity
            
                    
        # place new orders
        for node in self.order_sequence[:self.player_index]:
            for supplier in self.suppliers[node]:
                arc = self.arcs[(supplier, node)] # TODO: need to send multiple arcs together in the multi-supplier setting
                states = self.get_states(node, period)
                self.nodes[node].place_order(states, arc, period)
                
                
                
    def player_action(self, period, order_quantity):
        node = self.player
        for supplier in self.suppliers[node]:
            
            arc = self.arcs[(supplier, node)] # TODO: need to send multiple arcs together in the multi-supplier setting
            states = self.get_states(node, period)
            self.nodes[node].place_order(states, arc, period, order_quantity=order_quantity)
            
        
#         self.summary()
    
                
        
    def after_action(self, period): 
        # place new orders
        for node in self.order_sequence[self.player_index+1:]:
            for supplier in self.suppliers[node]:
                
                arc = self.arcs[(supplier, node)] # TODO: need to send multiple arcs together in the multi-supplier setting
                states = self.get_states(node, period)                
                self.nodes[node].place_order(states, arc, period)

                
        # fill orders
        for node in self.shipment_sequence:
            self.nodes[node].unfilled_demand = 0
            for customer in self.customers[node]:
                self.nodes[node].unfilled_demand += self.arcs[(node, customer)].fill_orders(self.nodes[node])
            

                    
    def cost_keeping(self):
        
        c_h = 0
        c_s = 0
        
        internal_nodes = [node for key, node in self.nodes.items() if (not node.supply_source) and (not node.demand_source)]
        for node in internal_nodes:
            
            # record holding cost
            node.current_holding_cost = -node.current_inventory * node.unit_holding_cost
            
            # record stockout cost
            node.current_stockout_cost = -node.unfilled_demand * node.unit_stockout_cost 
            
            
            # keep_cost_history
            node.holding_cost_history.append(node.current_holding_cost)
            node.stockout_cost_history.append(node.current_stockout_cost)
    
            c_h += node.current_holding_cost
            c_s += node.current_stockout_cost
            
        return c_h + c_s
    
    

    
    
class InventoryManagementEnv():
    
    def __init__(self, supply_chain_network):
        self.scn = supply_chain_network
        self.terminal = False
        

    def reset(self):
        self.terminal = False
        self.scn.reset()
        self.period = 0
        
        self.scn.before_action(self.period)
        
        states = self.scn.get_states(self.scn.player, self.period)
#         states['period'] = self.period
        
        return states
        
    
    def step(self, quantity, verbose=True):
        
        
        self.scn.player_action(self.period, quantity)
        self.scn.after_action(self.period)

        cost = self.scn.cost_keeping()
        
        self.period += 1
        
        if self.period < self.scn.max_period:
            self.scn.before_action(self.period)
        else:
            self.terminal = True
            
            
        states = self.scn.get_states(self.scn.player, self.period)
#         states['period'] = self.period
    
        return states, cost, self.terminal 
