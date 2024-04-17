from oscar.core.loading import get_class

from oscar_elasticsearch.exceptions import ElasticSearchQueryException
from oscar_elasticsearch.search import settings


paginate_result = get_class("search.api.pagination", "paginate_result")
es = get_class("search.backend", "es")


def get_search_query(
    search_fields=[], query_string=None, search_type=None, search_operator=None
):
    if query_string:
        return [
            {
                "multi_match": {
                    "query": query_string,
                    "type": search_type,
                    "operator": search_operator,
                    "fields": search_fields,
                }
            }
        ]

    else:
        return {"match_all": {}}


def get_search_body(
    _from,
    size,
    search_fields=[],
    query_string=None,
    filters=None,
    sort_by=None,
    suggestion_field_name=None,
    search_type=None,
    search_operator=None,
    aggs=None,
):
    body = {
        "query": {
            "bool": {
                "must": get_search_query(
                    search_fields, query_string, search_type, search_operator
                ),
                "filter": filters,
            }
        },
        "from": _from,
        "size": size,
    }

    if sort_by:
        body["sort"] = sort_by

    if aggs:
        body["aggs"] = aggs

    if suggestion_field_name and query_string:
        body["suggest"] = {
            suggestion_field_name: {
                "prefix": query_string,
                "term": {"field": suggestion_field_name},
            }
        }

    return body


def get_elasticsearch_aggs(aggs_definitions):
    aggs = {}

    for facet_definition in aggs_definitions:
        name = facet_definition["name"]
        facet_type = facet_definition["type"]
        if facet_type == "term":
            terms = {"terms": {"field": name}}

            if "order" in facet_definition:
                terms["terms"]["order"] = {"_key": facet_definition.get("order", "asc")}

            aggs[name] = terms
        elif facet_type == "range":
            ranges_definition = facet_definition["ranges"]
            ranges = [
                (
                    {"to": ranges_definition[i]}
                    if i == 0
                    else {
                        "from": ranges_definition[i - 1],
                        "to": ranges_definition[i],
                    }
                )
                for i in range(len(ranges_definition))
            ]

            ranges.append({"from": ranges_definition[-1]})

            aggs[name] = {"range": {"field": name, "ranges": ranges}}

    return aggs


def search(
    index,
    _from,
    size,
    Model,
    search_fields=[],
    query_string=None,
    filters=None,
    sort_by=None,
    suggestion_field_name=None,
    search_type=settings.SEARCH_QUERY_TYPE,
    search_operator=settings.SEARCH_QUERY_OPERATOR,
):
    body = get_search_body(
        _from,
        size,
        search_fields=search_fields,
        query_string=query_string,
        filters=filters,
        sort_by=sort_by,
        suggestion_field_name=suggestion_field_name,
        search_type=search_type,
        search_operator=search_operator,
    )

    result = es.search(index=index, body=body)

    status = search_results["status"]

    if status > 200:
        raise ElasticSearchQueryException(
            "Something went wrong during elasticsearch query", search_results
        )

    return paginate_result(result, Model, size)


def facet_search(
    index,
    _from,
    size,
    Model,
    search_fields,
    query_string=None,
    default_filters=None,
    facet_filters=None,
    sort_by=None,
    suggestion_field_name=None,
    search_type=settings.SEARCH_QUERY_TYPE,
    search_operator=settings.SEARCH_QUERY_OPERATOR,
    aggs_definitions=None,
):

    aggs = get_elasticsearch_aggs(aggs_definitions)

    index_body = {"index": index}

    result_body = get_search_body(
        _from,
        size,
        search_fields=search_fields,
        query_string=query_string,
        filters=default_filters + facet_filters,
        sort_by=sort_by,
        suggestion_field_name=suggestion_field_name,
        search_type=settings.SEARCH_QUERY_TYPE,
        search_operator=settings.SEARCH_QUERY_OPERATOR,
        aggs=aggs,
    )

    unfiltered_body = get_search_body(
        0,
        0,
        search_fields=search_fields,
        query_string=query_string,
        filters=default_filters,
        sort_by=sort_by,
        suggestion_field_name=suggestion_field_name,
        search_type=settings.SEARCH_QUERY_TYPE,
        search_operator=settings.SEARCH_QUERY_OPERATOR,
        aggs=aggs,
    )

    multi_body = [
        index_body,
        result_body,
        index_body,
        unfiltered_body,
    ]

    search_results, unfiltered_result = es.msearch(body=multi_body)["responses"]

    search_result_status = search_results["status"]
    unfiltered_result_status = unfiltered_result["status"]

    if search_result_status > 200:
        raise ElasticSearchQueryException(
            "Something went wrong during elasticsearch query", search_results
        )
    elif unfiltered_result_status > 200:
        raise ElasticSearchQueryException(
            "Something went wrong during elasticsearch query", unfiltered_result_status
        )

    return (
        paginate_result(search_results, Model, size),
        search_results,
        unfiltered_result,
    )
