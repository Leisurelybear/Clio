"""Tests for clio/ui/router.py — Route, Router, dispatch."""

from __future__ import annotations

from clio.ui.router import Route, Router


def _handler_dummy(self, qs):
    return "dummy"


def _handler_with_param(self, qs, name):
    return f"param:{name}"


def _handler_two_params(self, qs, a, b):
    return f"two:{a},{b}"


def _handler_payload(self, qs, obj):
    return f"body:{obj}"


class TestRoute:
    def test_static_route(self):
        router = Router()
        router.add(Route("GET", "/api/config", _handler_dummy))
        handler, kwargs, route = router.dispatch("GET", "/api/config")
        assert handler is _handler_dummy
        assert kwargs == {}
        assert route is not None

    def test_param_route(self):
        router = Router()
        router.add(Route("GET", "/api/vmeta/{stem}", _handler_with_param))
        handler, kwargs, route = router.dispatch("GET", "/api/vmeta/GL010695")
        assert handler is _handler_with_param
        assert kwargs == {"stem": "GL010695"}

    def test_param_route_two_params(self):
        router = Router()
        router.add(Route("GET", "/api/{a}/{b}", _handler_two_params))
        handler, kwargs, route = router.dispatch("GET", "/api/foo/bar")
        assert handler is _handler_two_params
        assert kwargs == {"a": "foo", "b": "bar"}

    def test_param_route_multiple(self):
        router = Router()
        router.add(Route("PUT", "/api/prompts/{name}", _handler_with_param))
        handler, kwargs, route = router.dispatch("PUT", "/api/prompts/day1")
        assert handler is _handler_with_param
        assert kwargs == {"name": "day1"}

    def test_no_match_returns_none(self):
        router = Router()
        router.add(Route("GET", "/api/config", _handler_dummy))
        handler, kwargs, route = router.dispatch("GET", "/api/unknown")
        assert handler is None

    def test_method_mismatch_returns_none(self):
        router = Router()
        router.add(Route("GET", "/api/config", _handler_dummy))
        handler, kwargs, route = router.dispatch("POST", "/api/config")
        assert handler is None

    def test_prefix_route(self):
        router = Router()
        router.add(Route("GET", "/static/", _handler_dummy, prefix=True))
        handler, kwargs, route = router.dispatch("GET", "/static/js/app.js")
        assert handler is _handler_dummy
        assert kwargs == {}

    def test_prefix_route_exact_path(self):
        router = Router()
        router.add(Route("GET", "/", _handler_dummy, prefix=False))
        handler, kwargs, route = router.dispatch("GET", "/")
        assert handler is _handler_dummy

    def test_add_list(self):
        router = Router()
        router.add_list(
            [
                Route("GET", "/api/config", _handler_dummy),
                Route("GET", "/api/videos", _handler_dummy),
            ]
        )
        h1, _, _ = router.dispatch("GET", "/api/config")
        h2, _, _ = router.dispatch("GET", "/api/videos")
        assert h1 is _handler_dummy
        assert h2 is _handler_dummy

    def test_get_policy_returns_route_auth(self):
        router = Router()
        router.add(Route("GET", "/api/config", _handler_dummy, auth_required=True))
        policy = router.get_policy("GET", "/api/config")
        assert policy.auth_required is True

    def test_get_policy_prefix(self):
        router = Router()
        router.add(Route("GET", "/static/", _handler_dummy, auth_required=False, prefix=True))
        policy = router.get_policy("GET", "/static/js/app.js")
        assert policy.auth_required is False

    def test_get_policy_unknown_api_returns_auth(self):
        router = Router()
        policy = router.get_policy("GET", "/api/unknown")
        assert policy.auth_required is True

    def test_get_policy_unknown_non_api_returns_no_auth(self):
        router = Router()
        policy = router.get_policy("GET", "/some/page.html")
        assert policy.auth_required is False

    def test_param_with_reserved_chars(self):
        router = Router()
        router.add(Route("GET", "/api/vmeta/{stem}", _handler_with_param))
        handler, kwargs, route = router.dispatch("GET", "/api/vmeta/GL01.0695")
        assert handler is _handler_with_param
        assert kwargs == {"stem": "GL01.0695"}
