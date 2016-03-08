from SPARQLWrapper import SPARQLWrapper, JSON, XML, N3, RDF
import pdb
import csv
import re

#parse query, make sure it is well formed
#for each part of the query
	#get all descendants
	#eliminate everything that does not fit (or does if it is a not query)
#return everything left

#format for input (X:A (AND|OR) NOT? Y:B) etc
#class Command:
	#def __init__(self, input):



class Query:
	def __init__(self):
		self.SnoMedGraph = "http://bioportal.bioontology.org/ontologies/SNOMEDCT"
		self.SnoMedPURL = "http://purl.bioontology.org/ontology/SNOMEDCT/"

		self.OBIGraph = "http://bioportal.bioontology.org/ontologies/OBI"
		self.OBIPURL = "http://purl.obolibrary.org/obo/"

	def query(self, queryString):
		sparql_service = "http://sparql.bioontology.org/sparql/"

		api_key = "7876def4-91ba-4ef2-85d4-8bf5770329dd"

		sparql = SPARQLWrapper(sparql_service)
		sparql.addCustomParameter("apikey",api_key)
		sparql.setQuery(queryString)
		sparql.setReturnFormat(JSON)
		results = sparql.query().convert()
		return results['results']['bindings']

	def getPrefix(self, category):
		if category.upper() == "CONDITION":
			graph = self.SnoMedPURL
		elif category.upper() == "SOURCEORGANISM":
			graph = self.OBIPURL

		return graph

	def getGraph(self, category):
		if category.upper() == "CONDITION":
			graph = self.SnoMedGraph
		elif category.upper() == "SOURCEORGANISM":
			graph = self.OBIGraph

		return graph

	def getBaseQuery(self, category, id):
		graph = self.getGraph(category)
		queryString = """
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

SELECT DISTINCT ?x ?label
FROM <%s>
FROM <http://bioportal.bioontology.org/ontologies/globals>
WHERE
{
    ?x rdfs:subClassOf <%s> .
    ?x skos:prefLabel ?label.
}""" % (graph, id)

		return queryString

	def getQueryNameString(self, category, name):
		graph = self.getGraph(category)

		queryString = """ 
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

SELECT DISTINCT ?x ?label
FROM <%s>
FROM <http://bioportal.bioontology.org/ontologies/globals>
WHERE
{
    ?y skos:prefLabel ?name .
    FILTER (CONTAINS ( UCASE(str(?name)), "%s") ) .
    ?x rdfs:subClassOf ?y .
    ?x skos:prefLabel ?label
}
""" % (graph, name)
	
		return queryString

	def getQueryIDString(self, category, id):
		graph = self.getGraph(category)
		pref = self.getPrefix(category)
		queryString = """
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX pref: <%s>

SELECT DISTINCT ?x ?label
FROM <%s>
FROM <http://bioportal.bioontology.org/ontologies/globals>
WHERE
{
    ?x rdfs:subClassOf pref:%s .
    ?x skos:prefLabel ?label
}""" % (pref, graph, id)

		return queryString


class Node:
		def __init__(self, input, Querier):
			self.query = Querier
			self.NotNode = False
			self.children = []

			if len(input) == 1:
				self.parseTerm(input)
			else:
				for i, value in enumerate(input):
					if value.upper() == "AND" or value.upper() == "OR":
						if i == 0:
							raise ValueError ("Can't start with AND|OR")

						self.children.append(Node(input[:i], Querier))
						self.children.append(Node(input[i+1:], Querier))
						self.join = value.upper()
						return

				if input[0].upper() == "NOT":
					self.NotNode = True
					input = input[1:]
				if len(input) > 1:	
					self.parseTerm([" ".join(input)])
				else:
					self.parseTerm(input)


		def parseTerm(self, input):
			values = input[0].split(":")
			if len(values) != 2:
				raise ValueError("Need input with format Property:Value")

			matches = re.match("(.*)(Name|ID)", values[0])

			if len(matches.groups()) != 2:
				raise ValueError("Improper Property Name %s" % values[0])

			self.type = matches.group(2)
			self.category = matches.group(1)
			self.column = values[0]
			self.term = values[1]

			queryString = self.getInitialQueryString(self.term)
			queue = query.query(queryString)
			self.options = [self.term]

			self.queryTerm(queue, 0)


		def getInitialQueryString(self, term):
			if self.type == "ID":
				return query.getQueryIDString(self.category, term)
			else:
				return query.getQueryNameString(self.category, term)

		def queryTerm(self, queue, depth):
			if depth >= 4:
				print "Stopping searching at depth 4"
				return

			newQueue = []

			for term in queue:
				results = query.query(query.getBaseQuery(self.category, term['x']['value']))
				newQueue += results
				for result in results:
					if self.type.upper() == "ID":
						matches = re.match(".*/([^/]+)$", result['x']['value'])
						id = matches.group(1)
						self.options.append(id)
					elif self.type.upper() == "NAME":
						self.options.append(result['label']['value'])

			if not newQueue:
				return

			self.queryTerm(newQueue, depth + 1)

		def pprint(self):
			if not self.children:
				print """
				type: %s
				category: %s
				term: %s """ % (self.type, self.category, self.term)

				for option in self.options:
					print "option: %s" % option['label']['value']
			else:
				self.children[0].pprint()
				print " " + self.join + " " 
				self.children[1].pprint()


		def eval(self, instances):
			results = []

			if self.children:
				if self.join == 'AND':
					childSet1 = self.children[0].eval(instances)
					if childSet1:
						results = self.children[1].eval(childSet1)
					else:
						return []
				elif self.join == 'OR':
					childSet1 = self.children[0].eval(instances)
					childSet2 = self.children[1].eval(instances)
					results = childSet1 + childSet2
				else:
					raise ValueError('children in a command node without a join')

			else:
				for instance in instances:
					if instance[self.column] in self.options and not self.NotNode:
						results.append(instance)
					elif instance[self.column] not in self.options and self.NotNode:
						results.append(instance)

			return results


class GDO:
	def __init__(self):
		self.instances = []

	#parse our csv into objects that we can store
	def parseCSV(self, filename):
		self.instances
		with open(filename, 'rb') as csvfile:
			reader = csv.DictReader(csvfile)
			for line in reader:
				self.instances.append(line)

	def getInstances(self):
		return self.instances

if __name__ == "__main__":
    query = Query()
    node = Node("ConditionID:236570004 AND NOT ConditionID:236574008".split(), query)
    gdo = GDO()
    gdo.parseCSV("annotations_bmi210.csv")
    results = node.eval(gdo.getInstances())

    for result in results:
    	print result["Experiment"]


