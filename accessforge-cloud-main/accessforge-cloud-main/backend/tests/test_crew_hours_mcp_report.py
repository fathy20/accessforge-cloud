import json
import unittest
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.statistics.crew_hours.config import LeonConfiguration
from backend.statistics.crew_hours.errors import (
    CrewHoursCapabilityError,
    LeonContractError,
    LeonResponseError,
    LeonTimeoutError,
)
from backend.statistics.crew_hours.mcp_report import (
    OfficialMcpReport,
    _aggregate_report_rows,
    _parse_block_time,
    fetch_official_totals,
)
from backend.statistics.crew_hours.response_models import LeonFlight
from backend.statistics.crew_hours.service import (
    LEON_POSITION_GROUPS,
    LiveCrewHoursService,
    _position_group,
)
from backend.statistics.crew_hours.token_provider import LeonAccessTokenProvider
from backend.statistics.crew_hours.transport import FakeLeonTransport, LeonRawResponse


class TestMcpReport(unittest.TestCase):
    def _transport(self, report_rows=None, report_body=None):
        if report_body is None:
            report_body = json.dumps({
                "jsonrpc": "2.0", "id": 2,
                "result": {"content": [{"type": "text", "text": json.dumps({"data": report_rows})}]},
            })
        return FakeLeonTransport(responses=[
            LeonRawResponse(200, "t" * 72),
            LeonRawResponse(200, json.dumps({
                "jsonrpc": "2.0", "id": 1,
                "result": {"protocolVersion": "2025-03-26"},
            })),
            LeonRawResponse(200, report_body, {"content-type": "text/event-stream"}),
        ])

    def _fetch_body(self, body):
        transport = self._transport(report_body=body)
        config = LeonConfiguration(
            "https://rsx.leon.aero",
            "refresh-token",
            mcp_url="https://mcp.test.example/mcp",
        )
        return fetch_official_totals(
            config,
            transport,
            LeonAccessTokenProvider(config, transport),
            "2026-06-01",
            "2026-06-30",
        )

    @staticmethod
    def _report_body(rows, *, text_mode="object"):
        payload = {"records": rows, "recordsCount": len(rows)}
        if text_mode == "array":
            text = json.dumps(rows)
        elif text_mode == "nested":
            text = json.dumps(json.dumps(payload))
        elif text_mode == "plain":
            text = "unsupported report text"
        else:
            text = json.dumps(payload)
        return json.dumps({
            "jsonrpc": "2.0",
            "id": 2,
            "result": {"content": [{"type": "text", "text": text}]},
        })

    def test_fetches_and_aggregates_official_block_time_by_crew_code(self):
        transport = self._transport([
            {"scope_row_unique_id": "leg-1", "crew_codes": ["AKA", "AHU"], "crew_names": ["Ahmed Kamel", "Amr Hussien"], "blockTimeJourneyLog": "01:30"},
            {"scope_row_unique_id": "leg-2", "crew_codes": ["AKA"], "crew_names": ["Ahmed Kamel"], "blockTimeJourneyLog": "94:15"},
            {"scope_row_unique_id": "leg-3", "crew_codes": ["AHU"], "crew_names": ["Amr Hussien"], "blockTimeJourneyLog": "84:15"},
        ])
        totals = fetch_official_totals(
            LeonConfiguration("https://rsx.leon.aero", "refresh-token", mcp_url="https://mcp.test.example/mcp"),
            transport,
            LeonAccessTokenProvider(LeonConfiguration("https://rsx.leon.aero", "refresh-token", mcp_url="https://mcp.test.example/mcp"), transport),
            "2026-06-01",
            "2026-06-30",
        )

        self.assertEqual(totals, {"AKA": "95:45", "AHU": "85:45"})
        self.assertEqual(dict(totals), {"AKA": "95:45", "AHU": "85:45"})
        self.assertEqual(totals.get("AKA"), "95:45")
        self.assertEqual(totals.total_minutes, {"AKA": 5745, "AHU": 5145})
        self.assertEqual(len(transport.calls), 3)
        self.assertEqual(transport.calls[1].url, "https://mcp.test.example/mcp")
        self.assertIn("Accept", transport.calls[1].header_names)
        self.assertIn("Accept", transport.calls[2].header_names)
        self.assertEqual(transport.calls[2].json_body["method"], "tools/call")
        arguments = transport.calls[2].json_body["params"]["arguments"]
        self.assertEqual(arguments["dateFilter"]["start"], "2026-05-30T00:00:00Z")
        self.assertEqual(arguments["dateFilter"]["end"], "2026-07-02T23:59:59Z")
        self.assertEqual(arguments["columnList"], [
            "scope_row_unique_id",
            "crew_codes",
            "blockTimeJourneyLog",
            "unique_id",
            "crew_names",
            "crew_position_names",
            "date_STD_log_UTC",
            "registration",
            "acftType",
            "flightNo",
            "jl_adep_preferred_code",
            "jl_ades_preferred_code",
            "JL_STD_UTC",
            "JL_STA_UTC",
            "positioning_crew",
        ])
        for filter_name in (
            "acftNidList",
            "crewMemberNidList",
            "adepLocationNidList",
            "adesLocationNidList",
            "airportLocationNidList",
            "isCanceled",
            "permitsCountryList",
        ):
            self.assertIn(filter_name, arguments)
            self.assertIsNone(arguments[filter_name])
        self.assertEqual(transport.calls[0].form_field_names, ("refresh_token",))

    def test_block_time_parser_accepts_unbounded_hours_and_zero_seconds(self):
        self.assertEqual(_parse_block_time("5:50"), 350)
        self.assertEqual(_parse_block_time("05:50"), 350)
        self.assertEqual(_parse_block_time("95:45"), 5745)
        self.assertEqual(_parse_block_time("3452:25"), 207145)
        self.assertEqual(_parse_block_time("05:25:00"), 325)

    def test_block_time_parser_rejects_non_zero_seconds_without_the_value(self):
        with self.assertRaises(LeonContractError) as raised:
            _parse_block_time("05:25:30")
        self.assertEqual(
            str(raised.exception),
            "LEON MCP report blockTimeJourneyLog carried unsupported non-zero seconds.",
        )
        self.assertNotIn("05:25:30", str(raised.exception))

    def test_block_time_parser_rejects_bad_minutes_and_malformed_values(self):
        for value in ("5:60", "abc"):
            with self.subTest(value=value):
                with self.assertRaises(LeonContractError) as raised:
                    _parse_block_time(value)
                self.assertNotIn(value, str(raised.exception))

    def test_invalid_block_time_is_rejected_without_secret_leakage(self):
        transport = self._transport([
            {"scope_row_unique_id": "leg-invalid", "crew_codes": ["AKA"], "blockTimeJourneyLog": "not-a-duration"},
        ])
        provider = LeonAccessTokenProvider(
            LeonConfiguration("https://rsx.leon.aero", "refresh-token", mcp_url="https://mcp.test.example/mcp"),
            transport,
        )
        with self.assertRaises(LeonContractError) as raised:
            fetch_official_totals(
                LeonConfiguration("https://rsx.leon.aero", "refresh-token", mcp_url="https://mcp.test.example/mcp"),
                transport,
                provider,
                "2026-06-01",
                "2026-06-30",
            )
        self.assertNotIn("refresh-token", str(raised.exception))


    def test_report_object_inside_text_is_parsed(self):
        totals = self._fetch_body(self._report_body([{"scope_row_unique_id": "leg-object", "crew_codes": ["AKA"], "blockTimeJourneyLog": "01:30"}]))
        self.assertEqual(totals, {"AKA": "1:30"})

    def test_content_text_array_is_parsed(self):
        totals = self._fetch_body(self._report_body([{"scope_row_unique_id": "leg-array", "crew_codes": ["AKA"], "blockTimeJourneyLog": "01:30"}], text_mode="array"))
        self.assertEqual(totals, {"AKA": "1:30"})

    def test_nested_json_string_is_decoded_once(self):
        totals = self._fetch_body(self._report_body([{"scope_row_unique_id": "leg-nested", "crew_codes": ["AKA"], "blockTimeJourneyLog": "01:30"}], text_mode="nested"))
        self.assertEqual(totals, {"AKA": "1:30"})

    def test_sse_json_rpc_result_is_parsed(self):
        rpc = self._report_body([{"scope_row_unique_id": "leg-sse", "crew_codes": ["AKA"], "blockTimeJourneyLog": "01:30"}])
        body = "event: message\ndata: " + rpc + "\n\n"
        self.assertEqual(self._fetch_body(body), {"AKA": "1:30"})

    def test_multiple_sse_events_select_result_event(self):
        rpc = self._report_body([{"scope_row_unique_id": "leg-progress", "crew_codes": ["AKA"], "blockTimeJourneyLog": "01:30"}])
        body = "data: " + json.dumps({"jsonrpc": "2.0", "method": "progress"}) + "\n\n" + "data: " + rpc
        self.assertEqual(self._fetch_body(body), {"AKA": "1:30"})

    def test_resource_text_is_parsed(self):
        text = json.dumps({"records": [{"scope_row_unique_id": "leg-resource", "crew_codes": ["AKA"], "blockTimeJourneyLog": "01:30"}]})
        body = json.dumps({"jsonrpc": "2.0", "id": 2, "result": {"content": [{"type": "resource", "resource": {"text": text}}]}})
        self.assertEqual(self._fetch_body(body), {"AKA": "1:30"})

    def test_malformed_sse_is_rejected_without_raw_payload(self):
        with self.assertRaises(LeonResponseError) as raised:
            self._fetch_body("event: message\ndata: not-json\n")
        self.assertNotIn("not-json", str(raised.exception))

    def test_malformed_json_text_is_rejected(self):
        body = json.dumps({"jsonrpc": "2.0", "id": 2, "result": {"content": [{"type": "text", "text": "{not-json"}]}})
        with self.assertRaises(LeonResponseError):
            self._fetch_body(body)

    def test_unsupported_plain_text_is_rejected(self):
        with self.assertRaises(LeonResponseError):
            self._fetch_body(self._report_body([], text_mode="plain"))

    def test_missing_crew_column_is_rejected(self):
        body = self._report_body([
            {
                "scope_row_unique_id": "leg-anchor",
                "crew_codes": ["ANCHOR"],
                "blockTimeJourneyLog": "",
            },
            {"scope_row_unique_id": "leg-missing-crew", "blockTimeJourneyLog": "01:00"},
        ])
        with self.assertRaises(LeonContractError) as raised:
            self._fetch_body(body)
        self.assertEqual(
            str(raised.exception),
            "LEON MCP report row was missing required column 'crew_codes'.",
        )

    def test_capability_and_contract_errors_remain_distinct(self):
        self.assertFalse(issubclass(CrewHoursCapabilityError, LeonContractError))

        body = self._report_body([
            {
                "scope_row_unique_id": "leg-anchor",
                "crew_codes": ["ANCHOR"],
                "blockTimeJourneyLog": "",
            },
            {"scope_row_unique_id": "leg-missing-crew", "blockTimeJourneyLog": "01:00"},
        ])
        with self.assertRaises(LeonContractError) as raised:
            self._fetch_body(body)
        self.assertNotIsInstance(raised.exception, CrewHoursCapabilityError)
        self.assertEqual(
            str(raised.exception),
            "LEON MCP report row was missing required column 'crew_codes'.",
        )

    def test_missing_block_time_column_is_rejected(self):
        body = self._report_body([{"scope_row_unique_id": "leg-missing-block", "crew_codes": ["AKA"]}])
        with self.assertRaises(LeonContractError) as raised:
            self._fetch_body(body)
        self.assertEqual(
            str(raised.exception),
            "LEON MCP report row was missing required column 'blockTimeJourneyLog'.",
        )

    def test_missing_scope_row_unique_id_is_rejected(self):
        body = self._report_body([{"crew_codes": ["AKA"], "blockTimeJourneyLog": "01:00"}])
        with self.assertRaises(LeonContractError) as raised:
            self._fetch_body(body)
        self.assertEqual(
            str(raised.exception),
            "LEON MCP report row was missing required column 'scope_row_unique_id'.",
        )

    def test_non_mapping_report_row_is_rejected_with_shape_error(self):
        with self.assertRaises(LeonContractError) as raised:
            _aggregate_report_rows(["malformed-row"])
        message = str(raised.exception)
        self.assertEqual(message, "LEON MCP report row had an invalid shape.")
        self.assertNotIn("scope_row_unique_id", message)
        self.assertNotIn("crew_codes", message)
        self.assertNotIn("blockTimeJourneyLog", message)
        self.assertNotIn("malformed-row", message)

    def test_specific_row_anchor_skips_summary_sibling_and_finds_real_rows(self):
        real_rows = [{
            "scope_row_unique_id": "leg-real-row",
            "crew_codes": ["AKA"],
            "blockTimeJourneyLog": "01:30",
        }]
        body = json.dumps({
            "jsonrpc": "2.0",
            "id": 2,
            "result": {"content": [{
                "type": "text",
                "text": json.dumps({
                    "data": {
                        "blockTimeJourneyLog": "99:00",
                        "records": real_rows,
                    },
                }),
            }]},
        })
        self.assertEqual(self._fetch_body(body), {"AKA": "1:30"})

    def test_only_required_columns_are_sufficient_for_aggregation(self):
        body = self._report_body([{
            "scope_row_unique_id": "leg-required-only",
            "crew_codes": ["AKA"],
            "blockTimeJourneyLog": "01:30",
        }])
        self.assertEqual(self._fetch_body(body), {"AKA": "1:30"})

    def test_empty_block_time_is_skipped_without_changing_totals(self):
        body = self._report_body([
            {
                "scope_row_unique_id": "leg-empty-block",
                "crew_codes": ["SKIP"],
                "blockTimeJourneyLog": "",
            },
            {
                "scope_row_unique_id": "leg-null-block",
                "crew_codes": ["SKIP-NULL"],
                "blockTimeJourneyLog": None,
            },
            {
                "scope_row_unique_id": "leg-valid-block",
                "crew_codes": ["AKA"],
                "blockTimeJourneyLog": "01:30",
            },
        ])
        self.assertEqual(self._fetch_body(body), {"AKA": "1:30"})

    def test_required_column_error_does_not_leak_row_values(self):
        row = {
            "crew_codes": ["CREW_CODE_SENTINEL"],
            "crew_names": ["CREW_NAME_SENTINEL"],
            "blockTimeJourneyLog": "BLOCK_TIME_SENTINEL",
            "registration": "ROW_VALUE_SENTINEL",
        }
        with self.assertRaises(LeonContractError) as raised:
            self._fetch_body(self._report_body([row]))
        message = str(raised.exception)
        self.assertEqual(
            message,
            "LEON MCP report row was missing required column 'scope_row_unique_id'.",
        )
        for value in row["crew_codes"] + row["crew_names"] + [row["blockTimeJourneyLog"], row["registration"]]:
            self.assertNotIn(value, message)

    def test_duplicate_crew_code_in_one_row_counts_once(self):
        body = self._report_body([{"scope_row_unique_id": "leg-duplicate", "crew_codes": ["AKA", "AKA"], "blockTimeJourneyLog": "01:30"}])
        self.assertEqual(self._fetch_body(body), {"AKA": "1:30"})

    def test_total_above_24_hours_is_formatted_without_wrapping(self):
        body = self._report_body([
            {"scope_row_unique_id": "leg-long-1", "crew_codes": ["AKA"], "blockTimeJourneyLog": "23:30"},
            {"scope_row_unique_id": "leg-long-2", "crew_codes": ["AKA"], "blockTimeJourneyLog": "02:00"},
        ])
        self.assertEqual(self._fetch_body(body), {"AKA": "25:30"})

    def test_parse_error_does_not_include_raw_payload_or_token(self):
        body = self._report_body([], text_mode="plain")
        with self.assertRaises(LeonResponseError) as raised:
            self._fetch_body(body.replace("unsupported report text", "secret-person-payload"))
        self.assertNotIn("secret-person-payload", str(raised.exception))
        self.assertNotIn("refresh-token", str(raised.exception))

    def test_official_mcp_report_two_argument_constructor_derives_minutes(self):
        report = OfficialMcpReport({"AKA": "9:45"}, [])

        self.assertEqual(dict(report), {"AKA": "9:45"})
        self.assertEqual(report.get("AKA"), "9:45")
        self.assertEqual(report.total_minutes, {"AKA": 585})


class TestOfficialTotalsInService(unittest.TestCase):
    def test_group_totals_use_integer_minutes_for_returned_crew(self):
        rows = [
            {
                "scope_row_unique_id": "scope-cockpit-one",
                "crew_codes": ["COCKPIT-ONE"],
                "crew_names": ["Cockpit One"],
                "crew_position_names": ["CPT"],
                "blockTimeJourneyLog": "9:45",
            },
            {
                "scope_row_unique_id": "scope-cockpit-two",
                "crew_codes": ["COCKPIT-TWO"],
                "crew_names": ["Cockpit Two"],
                "crew_position_names": ["FO"],
                "blockTimeJourneyLog": "0:30",
            },
            {
                "scope_row_unique_id": "scope-cabin",
                "crew_codes": ["CABIN"],
                "crew_names": ["Cabin Member"],
                "crew_position_names": ["FA3"],
                "blockTimeJourneyLog": "1:00",
            },
            {
                "scope_row_unique_id": "scope-maintenance-one",
                "crew_codes": ["MAINTENANCE-ONE"],
                "crew_names": ["Maintenance One"],
                "crew_position_names": ["ENG1"],
                "blockTimeJourneyLog": "59:59",
            },
            {
                "scope_row_unique_id": "scope-maintenance-two",
                "crew_codes": ["MAINTENANCE-TWO"],
                "crew_names": ["Maintenance Two"],
                "crew_position_names": ["ENG2"],
                "blockTimeJourneyLog": "0:02",
            },
            {
                "scope_row_unique_id": "scope-unclassified",
                "crew_codes": ["UNCLASSIFIED"],
                "crew_names": ["Unclassified Member"],
                "crew_position_names": [None],
                "blockTimeJourneyLog": "2:03",
            },
            {
                "scope_row_unique_id": "scope-no-total",
                "crew_codes": ["NO-TOTAL"],
                "crew_names": ["No Total Member"],
                "crew_position_names": ["CPT"],
                "blockTimeJourneyLog": "1:00",
            },
        ]

        class FakeCrewClient:
            def fetch_official_totals(self, from_date, to_date):
                return OfficialMcpReport(
                    {
                        "COCKPIT-ONE": "9:45",
                        "COCKPIT-TWO": "0:30",
                        "CABIN": "1:00",
                        "MAINTENANCE-ONE": "59:59",
                        "MAINTENANCE-TWO": "0:02",
                        "UNCLASSIFIED": "2:03",
                    },
                    rows,
                    total_minutes={
                        "COCKPIT-ONE": 585,
                        "COCKPIT-TWO": 30,
                        "CABIN": 60,
                        "MAINTENANCE-ONE": 3599,
                        "MAINTENANCE-TWO": 2,
                        "UNCLASSIFIED": 123,
                    },
                )

        report = LiveCrewHoursService(FakeCrewClient()).get_crew_hours_report(
            "2026-06-01", "2026-06-30"
        )

        self.assertEqual(
            report.official_totals_by_position,
            {
                "Cockpit": "10:15",
                "Cabin": "1:00",
                "Maintenance": "60:01",
                "Unclassified": "2:03",
            },
        )
        self.assertEqual(report.official_totals_available, 6)
        self.assertEqual(report.official_totals_unavailable, 1)
        by_code = {member.person_code: member for member in report.crew_members}
        self.assertIsNone(by_code["UNCLASSIFIED"].position_type)
        self.assertIsNone(by_code["NO-TOTAL"].official_total)

    def test_group_total_above_24_hours_keeps_all_hours(self):
        rows = [{
            "scope_row_unique_id": "scope-long",
            "crew_codes": ["LONG"],
            "crew_position_names": ["CPT"],
            "blockTimeJourneyLog": "1234:56",
        }]

        class FakeCrewClient:
            def fetch_official_totals(self, from_date, to_date):
                return OfficialMcpReport(
                    {"LONG": "1234:56"},
                    rows,
                    total_minutes={"LONG": 1234 * 60 + 56},
                )

        report = LiveCrewHoursService(FakeCrewClient()).get_crew_hours_report(
            "2026-06-01", "2026-06-30"
        )
        self.assertEqual(report.official_totals_by_position, {"Cockpit": "1234:56"})

    def test_psn_is_excluded_while_other_approved_position_tokens_remain_included(self):
        durations = (
            ("PAD", "1:00"),
            ("PSN", "2:00"),
            ("FDP", "3:00"),
            ("FDPI", "4:00"),
            ("RMP", "5:00"),
            ("INSP", "6:00"),
        )
        rows = [
            {
                "scope_row_unique_id": f"scope-{token.lower()}",
                "crew_codes": ["POSITIONING"],
                "crew_position_names": [token],
                "blockTimeJourneyLog": block_time,
            }
            for token, block_time in durations
        ]
        formatted_totals, total_minutes = _aggregate_report_rows(rows)

        class FakeCrewClient:
            def fetch_official_totals(self, from_date, to_date):
                return OfficialMcpReport(formatted_totals, rows, total_minutes)

        report = LiveCrewHoursService(FakeCrewClient()).get_crew_hours_report(
            "2026-06-01", "2026-06-30"
        )

        self.assertEqual(formatted_totals, {"POSITIONING": "19:00"})
        self.assertEqual(total_minutes, {"POSITIONING": 1140})
        self.assertEqual(report.official_totals_by_position, {"Unclassified": "19:00"})
        for token, block_time in durations:
            with self.subTest(token=token):
                token_totals, token_minutes = _aggregate_report_rows(
                    [
                        {
                            "scope_row_unique_id": f"scope-{token.lower()}",
                            "crew_codes": ["POSITIONING"],
                            "crew_position_names": [token],
                            "blockTimeJourneyLog": block_time,
                        }
                    ]
                )
                if token == "PSN":
                    self.assertEqual(token_totals, {})
                    self.assertEqual(token_minutes, {})
                else:
                    expected_minutes = _parse_block_time(block_time)
                    self.assertEqual(token_totals, {"POSITIONING": block_time})
                    self.assertEqual(token_minutes, {"POSITIONING": expected_minutes})

    def test_mcp_rows_are_the_report_source_without_graphql_or_manual_adjustment(self):
        class FakeCrewClient:
            def __init__(self):
                self.flight_calls = 0

            def fetch_flights(self, from_date, to_date):
                self.flight_calls += 1
                raise LeonTimeoutError("GraphQL flightList timed out")

            def fetch_official_totals(self, from_date, to_date):
                return OfficialMcpReport(
                    {"AKA": "95:45", "AHU": "95:45"},
                    [
                        {
                            "scope_row_unique_id": "leg-1",
                            "crew_codes": ["AKA", "AHU", "AKA"],
                            "crew_names": ["Ahmed Kamel", "Amr Hussien", "Ahmed Kamel"],
                            "crew_position_names": ["CPT", "FO", "CPT"],
                            "blockTimeJourneyLog": "95:45",
                            "flightNo": "RS101",
                            "jl_adep_preferred_code": "HECA",
                            "jl_ades_preferred_code": "OEMA",
                            "JL_STD_UTC": "2026-06-01T08:00:00Z",
                            "JL_STA_UTC": "2026-06-01T11:30:00Z",
                        },
                    ],
                )

        client = FakeCrewClient()
        report = LiveCrewHoursService(client).get_crew_hours_report("2026-06-01", "2026-06-30")
        self.assertEqual(client.flight_calls, 0)
        self.assertEqual(report.source, "leon_mcp_report")
        self.assertEqual(report.hours_source_status, "official_mcp_report")
        self.assertEqual(report.total_crew, 2)
        self.assertEqual(report.total_flights, 1)
        by_code = {member.person_code: member for member in report.crew_members}
        self.assertEqual(by_code["AKA"].official_total, "95:45")
        self.assertEqual(by_code["AKA"].raw_official_total, "95:45")
        self.assertEqual(by_code["AKA"].flight_count, 1)
        self.assertEqual(by_code["AKA"].flights[0].flight_nid, "leg-1")
        self.assertEqual(by_code["AKA"].flights[0].flight_number, "RS101")
        self.assertEqual(by_code["AKA"].display_name, "Ahmed Kamel")
        self.assertEqual(by_code["AKA"].full_name, "Ahmed Kamel")
        self.assertEqual(by_code["AKA"].position_type, "Cockpit")
        self.assertIsNone(by_code["AKA"].reference_total)
        self.assertIsNone(by_code["AKA"].variance_minutes)

    def test_mcp_missing_display_name_uses_code_identity_without_graphql(self):
        class FakeCrewClient:
            def fetch_official_totals(self, from_date, to_date):
                return OfficialMcpReport(
                    {"NOC": "25:30"},
                    [{"scope_row_unique_id": "leg-noc", "crew_codes": ["NOC"], "blockTimeJourneyLog": "25:30"}],
                )

            def fetch_flights(self, from_date, to_date):
                raise LeonTimeoutError("GraphQL flightList timed out")

        with self.assertNoLogs("backend.statistics.crew_hours.service", level="WARNING"):
            report = LiveCrewHoursService(FakeCrewClient()).get_crew_hours_report(
                "2026-06-01", "2026-06-30"
            )
        self.assertEqual(report.crew_members[0].person_code, "NOC")
        self.assertEqual(report.crew_members[0].display_name, "NOC")
        self.assertIsNone(report.crew_members[0].full_name)
        self.assertIsNone(report.crew_members[0].position_type)
        self.assertEqual(report.crew_members[0].official_total, "25:30")

    def test_absent_optional_columns_log_once_at_info_for_the_whole_report(self):
        class FakeCrewClient:
            def fetch_official_totals(self, from_date, to_date):
                return OfficialMcpReport(
                    {"NOC": "02:00"},
                    [
                        {
                            "scope_row_unique_id": "leg-one",
                            "crew_codes": ["NOC"],
                            "blockTimeJourneyLog": "01:00",
                        },
                        {
                            "scope_row_unique_id": "leg-two",
                            "crew_codes": ["NOC"],
                            "blockTimeJourneyLog": "01:00",
                        },
                    ],
                )

        with self.assertLogs("backend.statistics.crew_hours.service", level="INFO") as logs:
            report = LiveCrewHoursService(FakeCrewClient()).get_crew_hours_report(
                "2026-06-01", "2026-06-30"
            )
        messages = "\n".join(logs.output)
        self.assertEqual(messages.count("optional column 'crew_names'"), 1)
        self.assertEqual(messages.count("optional column 'crew_position_names'"), 1)
        self.assertNotIn("misaligned", messages)
        self.assertEqual(report.crew_members[0].display_name, "NOC")
        self.assertIsNone(report.crew_members[0].full_name)

    def test_absent_names_do_not_block_a_present_position_array(self):
        class FakeCrewClient:
            def fetch_official_totals(self, from_date, to_date):
                return OfficialMcpReport(
                    {"POSITIONED": "01:00"},
                    [{
                        "scope_row_unique_id": "scope-position-only",
                        "crew_codes": ["POSITIONED"],
                        "crew_position_names": ["FA3"],
                        "blockTimeJourneyLog": "01:00",
                    }],
                )

        with self.assertNoLogs("backend.statistics.crew_hours.service", level="WARNING"):
            member = LiveCrewHoursService(FakeCrewClient()).get_crew_hours_report(
                "2026-06-01", "2026-06-30"
            ).crew_members[0]
        self.assertEqual(member.display_name, "POSITIONED")
        self.assertIsNone(member.full_name)
        self.assertEqual(member.position_type, "Cabin")
        self.assertEqual(member.flights[0].position, "FA3")

    def test_padded_mcp_values_are_trimmed_before_response_mapping(self):
        class FakeCrewClient:
            def fetch_official_totals(self, from_date, to_date):
                return OfficialMcpReport(
                    {"PADDED": "01:00"},
                    [{
                        "scope_row_unique_id": "scope-padded",
                        "crew_codes": ["PADDED"],
                        "crew_names": ["  Some Name  "],
                        "crew_position_names": [" CPT "],
                        "blockTimeJourneyLog": "01:00",
                        "flightNo": "  RSX311  ",
                    }],
                )

        member = LiveCrewHoursService(FakeCrewClient()).get_crew_hours_report(
            "2026-06-01", "2026-06-30"
        ).crew_members[0]
        self.assertEqual(member.display_name, "Some Name")
        self.assertEqual(member.full_name, "Some Name")
        self.assertEqual(member.flights[0].flight_number, "RSX311")

    def test_mcp_row_maps_all_verified_columns_to_the_flight_item(self):
        class FakeCrewClient:
            def fetch_official_totals(self, from_date, to_date):
                return OfficialMcpReport(
                    {"MAP": "05:25"},
                    [{
                        "scope_row_unique_id": "scope-map",
                        "crew_codes": ["MAP"],
                        "blockTimeJourneyLog": "05:25",
                        "crew_names": ["Mapped Crew"],
                        "crew_position_names": ["FO"],
                        "date_STD_log_UTC": "01-06-2026",
                        "registration": "SU-MAP",
                        "acftType": "A320",
                        "flightNo": "RS-MAP",
                        "jl_adep_preferred_code": "HECA",
                        "jl_ades_preferred_code": "OEMA",
                        "JL_STD_UTC": "08:00",
                        "JL_STA_UTC": "13:25",
                        "positioning_crew": [],
                        "flight_number": "must-not-be-used",
                        "adep": "must-not-be-used",
                        "ades": "must-not-be-used",
                        "OFF": "must-not-be-used",
                        "ON": "must-not-be-used",
                    }],
                )

        flight = LiveCrewHoursService(FakeCrewClient()).get_crew_hours_report(
            "2026-06-01", "2026-06-30"
        ).crew_members[0].flights[0]
        self.assertEqual(flight.flight_nid, "scope-map")
        self.assertEqual(flight.flight_number, "RS-MAP")
        self.assertEqual(flight.departure_airport, "HECA")
        self.assertEqual(flight.arrival_airport, "OEMA")
        self.assertEqual(flight.start_time_utc, "08:00")
        self.assertEqual(flight.end_time_utc, "13:25")
        self.assertEqual(flight.aircraft_reg, "SU-MAP")
        self.assertEqual(flight.aircraft_type, "A320")
        self.assertEqual(flight.flight_date, "01-06-2026")
        self.assertEqual(flight.block_time, "05:25")
        self.assertEqual(flight.position, "FO")
        self.assertFalse(flight.is_trn)
        self.assertFalse(hasattr(flight, "is_positioning"))

    def test_empty_verified_values_are_exposed_as_none(self):
        class FakeCrewClient:
            def fetch_official_totals(self, from_date, to_date):
                return OfficialMcpReport(
                    {},
                    [{
                        "scope_row_unique_id": "scope-empty-values",
                        "crew_codes": ["EMPTY"],
                        "blockTimeJourneyLog": "",
                        "crew_names": [""],
                        "crew_position_names": [""],
                        "date_STD_log_UTC": "",
                        "registration": "",
                        "acftType": "",
                        "flightNo": "",
                        "jl_adep_preferred_code": "",
                        "jl_ades_preferred_code": "",
                        "JL_STD_UTC": "",
                        "JL_STA_UTC": "",
                        "positioning_crew": [],
                    }],
                )

        member = LiveCrewHoursService(FakeCrewClient()).get_crew_hours_report(
            "2026-06-01", "2026-06-30"
        ).crew_members[0]
        self.assertEqual(member.display_name, "EMPTY")
        self.assertIsNone(member.full_name)
        self.assertIsNone(member.position_type)
        flight = member.flights[0]
        for field in (
            "flight_number",
            "departure_airport",
            "arrival_airport",
            "start_time_utc",
            "end_time_utc",
            "aircraft_reg",
            "aircraft_type",
            "flight_date",
            "block_time",
        ):
            with self.subTest(field=field):
                self.assertIsNone(getattr(flight, field))

    def test_position_type_ties_break_by_first_seen_group(self):
        class FakeCrewClient:
            def fetch_official_totals(self, from_date, to_date):
                return OfficialMcpReport(
                    {"MIXED": "02:00"},
                    [
                        {
                            "scope_row_unique_id": "scope-first-position",
                            "crew_codes": ["MIXED"],
                            "crew_names": ["Mixed Member"],
                            "crew_position_names": ["CPT"],
                            "blockTimeJourneyLog": "01:00",
                        },
                        {
                            "scope_row_unique_id": "scope-second-position",
                            "crew_codes": ["MIXED"],
                            "crew_names": ["Mixed Member"],
                            "crew_position_names": ["FA3"],
                            "blockTimeJourneyLog": "01:00",
                        },
                    ],
                )

        member = LiveCrewHoursService(FakeCrewClient()).get_crew_hours_report(
            "2026-06-01", "2026-06-30"
        ).crew_members[0]
        self.assertEqual(member.position_type, "Cockpit")

    def test_leon_declared_position_vocabulary_maps_to_its_declared_groups(self):
        expected_groups = {
            "Cockpit": frozenset({
                "CPT", "CPT2", "CPT3", "CPT4", "CPT5", "FE", "FO", "FO2", "FO3", "FO4",
                "INS", "LTC", "LTE", "LTI", "OBS", "OBS2", "SP", "STB", "TRE", "TRI",
            }),
            "Cabin": frozenset({
                "EFA", "EFA2", "FA1", "FA2", "FA3", "FA4", "FA5", "FA6", "FA7", "FA8",
                "FA9", "FA10", "FA11", "FA12", "FA13", "FA14", "FA15", "IFA", "IFA2", "SFA",
                "SFA2", "SFA3",
            }),
            "Maintenance": frozenset({"ENG1", "ENG2", "ENG3", "ENG4"}),
        }
        self.assertEqual(LEON_POSITION_GROUPS, expected_groups)
        self.assertEqual(sum(len(tokens) for tokens in expected_groups.values()), 46)
        for group, tokens in expected_groups.items():
            for token in tokens:
                with self.subTest(group=group, token=token):
                    self.assertEqual(_position_group(token), group)

    def test_known_unclassified_and_unverified_position_tokens_remain_unmapped(self):
        for token in ("PAD", "PSN", "FDP", "FDPI", "RMP", "INSP"):
            with self.subTest(token=token):
                self.assertIsNone(_position_group(token))
        self.assertIsNone(_position_group("CMD"))

    def test_fa15_uses_explicit_entry_and_fa16_uses_numeric_fallback(self):
        self.assertIn("FA15", LEON_POSITION_GROUPS["Cabin"])
        self.assertEqual(_position_group("FA15"), "Cabin")
        self.assertNotIn("FA16", LEON_POSITION_GROUPS["Cabin"])
        self.assertEqual(_position_group("FA16"), "Cabin")

    def test_unclassified_positions_log_once_with_sorted_tokens_and_no_personal_data(self):
        class FakeCrewClient:
            def fetch_official_totals(self, from_date, to_date):
                return OfficialMcpReport(
                    {"CREW-A": "02:00", "CREW-B": "02:00", "CREW-C": "02:00"},
                    [
                        {
                            "scope_row_unique_id": "scope-unclassified-one",
                            "crew_codes": ["CREW-A", "CREW-B"],
                            "crew_names": ["Alice Example", "Bob Example"],
                            "crew_position_names": ["PAD", "psn"],
                            "blockTimeJourneyLog": "01:00",
                        },
                        {
                            "scope_row_unique_id": "scope-unclassified-two",
                            "crew_codes": ["CREW-A", "CREW-C"],
                            "crew_names": ["Alice Example", "Carol Example"],
                            "crew_position_names": ["PAD", "FDP"],
                            "blockTimeJourneyLog": "01:00",
                        },
                    ],
                )

        with self.assertLogs("backend.statistics.crew_hours.service", level="INFO") as logs:
            LiveCrewHoursService(FakeCrewClient()).get_crew_hours_report(
                "2026-06-01", "2026-06-30"
            )
        unclassified_logs = [
            record for record in logs.records if "unclassified positions" in record.getMessage()
        ]
        self.assertEqual(len(unclassified_logs), 1)
        self.assertEqual(
            unclassified_logs[0].getMessage(),
            "LEON MCP report contained 3 crew with unclassified positions: ['FDP', 'PAD', 'PSN']",
        )
        for value in ("CREW-A", "CREW-B", "CREW-C", "Alice Example", "Bob Example", "Carol Example"):
            self.assertNotIn(value, unclassified_logs[0].getMessage())

    def test_reports_without_unclassified_positions_do_not_log_unclassified_line(self):
        class FakeCrewClient:
            def fetch_official_totals(self, from_date, to_date):
                return OfficialMcpReport(
                    {"KNOWN": "01:00"},
                    [{
                        "scope_row_unique_id": "scope-known",
                        "crew_codes": ["KNOWN"],
                        "crew_names": ["Known Crew"],
                        "crew_position_names": ["CPT"],
                        "blockTimeJourneyLog": "01:00",
                    }],
                )

        with self.assertNoLogs("backend.statistics.crew_hours.service", level="INFO"):
            LiveCrewHoursService(FakeCrewClient()).get_crew_hours_report(
                "2026-06-01", "2026-06-30"
            )

    def test_crew_arrays_are_expanded_index_by_index(self):
        class FakeCrewClient:
            def fetch_official_totals(self, from_date, to_date):
                return OfficialMcpReport(
                    {"C1": "01:00", "C2": "01:00", "C3": "01:00"},
                    [{
                        "scope_row_unique_id": "scope-aligned",
                        "crew_codes": ["C1", "C2", "C3"],
                        "crew_names": ["Bahaa Eldin Ibrahim", "Cabin Member", "Engineer Member"],
                        "crew_position_names": ["CPT", "FA3", "ENG1"],
                        "blockTimeJourneyLog": "01:00",
                    }],
                )

        report = LiveCrewHoursService(FakeCrewClient()).get_crew_hours_report(
            "2026-06-01", "2026-06-30"
        )
        by_code = {member.person_code: member for member in report.crew_members}
        self.assertEqual(by_code["C1"].display_name, "Bahaa Eldin Ibrahim")
        self.assertEqual(by_code["C1"].full_name, "Bahaa Eldin Ibrahim")
        self.assertEqual(by_code["C1"].position_type, "Cockpit")
        self.assertEqual(by_code["C1"].flights[0].position, "CPT")
        self.assertEqual(by_code["C2"].position_type, "Cabin")
        self.assertEqual(by_code["C2"].flights[0].position, "FA3")
        self.assertEqual(by_code["C3"].position_type, "Maintenance")
        self.assertEqual(by_code["C3"].flights[0].position, "ENG1")

    def test_misaligned_crew_arrays_degrade_one_row_and_continue(self):
        class FakeCrewClient:
            def fetch_official_totals(self, from_date, to_date):
                return OfficialMcpReport(
                    {"BAD": "01:00", "OK": "01:00", "GOOD": "01:00"},
                    [
                        {
                            "scope_row_unique_id": "scope-misaligned",
                            "crew_codes": ["BAD", "OK", "BAD"],
                            "crew_names": ["Bad Name", "Other Name"],
                            "crew_position_names": ["CPT", "FO", "CPT"],
                            "blockTimeJourneyLog": "01:00",
                        },
                        {
                            "scope_row_unique_id": "scope-good",
                            "crew_codes": ["GOOD"],
                            "crew_names": ["Good Name"],
                            "crew_position_names": ["FA3"],
                            "blockTimeJourneyLog": "01:00",
                        },
                    ],
                )

        with self.assertLogs("backend.statistics.crew_hours.service", level="WARNING") as logs:
            report = LiveCrewHoursService(FakeCrewClient()).get_crew_hours_report(
                "2026-06-01", "2026-06-30"
            )
        message = "\n".join(logs.output)
        self.assertIn("scope-misaligned", message)
        for value in ("BAD", "OK", "GOOD", "Bad Name", "Other Name", "Good Name", "01:00"):
            self.assertNotIn(value, message)
        by_code = {member.person_code: member for member in report.crew_members}
        for code in ("BAD", "OK"):
            self.assertEqual(by_code[code].display_name, code)
            self.assertIsNone(by_code[code].full_name)
            self.assertIsNone(by_code[code].position_type)
        self.assertEqual(by_code["GOOD"].display_name, "Good Name")
        self.assertEqual(by_code["GOOD"].position_type, "Cabin")

    def test_names_misaligned_preserves_aligned_source_position_on_flight(self):
        row = {
            "scope_row_unique_id": "scope-names-misaligned",
            "crew_codes": ["OPERATING", "PASSENGER"],
            "crew_names": ["Only One Name"],
            "crew_position_names": ["CPT", "PSN"],
            "blockTimeJourneyLog": "02:15",
        }
        formatted_totals, total_minutes = _aggregate_report_rows([row])
        self.assertEqual(formatted_totals, {"OPERATING": "2:15"})
        self.assertEqual(total_minutes, {"OPERATING": 135})

        class FakeCrewClient:
            def fetch_official_totals(self, from_date, to_date):
                return OfficialMcpReport(formatted_totals, [row], total_minutes)

        with self.assertLogs("backend.statistics.crew_hours.service", level="WARNING"):
            report = LiveCrewHoursService(FakeCrewClient()).get_crew_hours_report(
                "2026-06-01", "2026-06-30"
            )

        by_code = {member.person_code: member for member in report.crew_members}
        for code in ("OPERATING", "PASSENGER"):
            self.assertEqual(by_code[code].display_name, code)
            self.assertIsNone(by_code[code].full_name)
            self.assertIsNone(by_code[code].position_name)
            self.assertIsNone(by_code[code].position_type)

        self.assertEqual(by_code["OPERATING"].official_total, "2:15")
        self.assertIsNone(by_code["PASSENGER"].official_total)
        self.assertEqual(by_code["OPERATING"].flights[0].position, "CPT")
        self.assertEqual(by_code["PASSENGER"].flights[0].position, "PSN")

    def test_duplicate_code_uses_the_original_array_index_and_counts_once(self):
        class FakeCrewClient:
            def fetch_official_totals(self, from_date, to_date):
                return OfficialMcpReport(
                    {"DUP": "01:00"},
                    [{
                        "scope_row_unique_id": "scope-dedup",
                        "crew_codes": ["", "DUP", "DUP"],
                        "crew_names": ["Blank Slot", "First Duplicate", "Second Duplicate"],
                        "crew_position_names": ["ZZZ", "FO", "FA3"],
                        "blockTimeJourneyLog": "01:00",
                    }],
                )

        member = LiveCrewHoursService(FakeCrewClient()).get_crew_hours_report(
            "2026-06-01", "2026-06-30"
        ).crew_members[0]
        self.assertEqual(member.person_code, "DUP")
        self.assertEqual(member.display_name, "First Duplicate")
        self.assertEqual(member.position_type, "Cockpit")
        self.assertEqual(member.flight_count, 1)

    def test_position_filter_uses_leon_position_groups_and_counts_totals(self):
        class FakeCrewClient:
            def fetch_official_totals(self, from_date, to_date):
                return OfficialMcpReport(
                    {
                        "COCKPIT": "01:00",
                        "CABIN": "01:00",
                        "MAINT": "01:00",
                    },
                    [
                        {
                            "scope_row_unique_id": "scope-cockpit",
                            "crew_codes": ["COCKPIT"],
                            "crew_names": ["Cockpit Member"],
                            "crew_position_names": ["cPt"],
                            "blockTimeJourneyLog": "01:00",
                        },
                        {
                            "scope_row_unique_id": "scope-cabin",
                            "crew_codes": ["CABIN"],
                            "crew_names": ["Cabin Member"],
                            "crew_position_names": ["FA3"],
                            "blockTimeJourneyLog": "01:00",
                        },
                        {
                            "scope_row_unique_id": "scope-maintenance",
                            "crew_codes": ["MAINT"],
                            "crew_names": ["Maintenance Member"],
                            "crew_position_names": ["ENG1"],
                            "blockTimeJourneyLog": "01:00",
                        },
                        {
                            "scope_row_unique_id": "scope-unknown",
                            "crew_codes": ["UNKNOWN"],
                            "crew_names": ["Unknown Member"],
                            "crew_position_names": ["ZZZ"],
                            "blockTimeJourneyLog": "01:00",
                        },
                    ],
                )

        client = FakeCrewClient()
        all_members = LiveCrewHoursService(client).get_crew_hours_report(
            "2026-06-01", "2026-06-30"
        )
        all_by_code = {member.person_code: member for member in all_members.crew_members}
        self.assertEqual(all_by_code["COCKPIT"].position_type, "Cockpit")
        self.assertEqual(all_by_code["CABIN"].position_type, "Cabin")
        self.assertEqual(all_by_code["MAINT"].position_type, "Maintenance")
        self.assertIsNone(all_by_code["UNKNOWN"].position_type)

        cockpit = LiveCrewHoursService(client).get_crew_hours_report(
            "2026-06-01", "2026-06-30", position="Cockpit"
        )
        self.assertEqual([member.person_code for member in cockpit.crew_members], ["COCKPIT"])
        self.assertEqual(cockpit.records_count, 4)
        self.assertEqual(cockpit.total_flights, 1)
        self.assertEqual(cockpit.official_totals_available, 1)
        self.assertEqual(cockpit.official_totals_unavailable, 0)
        self.assertEqual(
            cockpit.official_totals_by_position,
            {
                "Cockpit": "1:00",
                "Cabin": "1:00",
                "Maintenance": "1:00",
            },
        )

    def test_records_count_differs_from_selected_flights_and_official_counts_are_explicit(self):
        class FakeCrewClient:
            def fetch_official_totals(self, from_date, to_date):
                return OfficialMcpReport(
                    {"AVAILABLE": "01:00"},
                    [
                        {
                            "scope_row_unique_id": "scope-available",
                            "crew_codes": ["AVAILABLE"],
                            "crew_names": ["Available Member"],
                            "crew_position_names": ["CPT"],
                            "blockTimeJourneyLog": "01:00",
                        },
                        {
                            "scope_row_unique_id": "scope-unavailable",
                            "crew_codes": ["UNAVAILABLE"],
                            "crew_names": ["Unavailable Member"],
                            "crew_position_names": ["FO"],
                            "blockTimeJourneyLog": "01:00",
                        },
                        {
                            "scope_row_unique_id": "scope-filtered",
                            "crew_codes": ["FILTERED"],
                            "crew_names": ["Filtered Member"],
                            "crew_position_names": ["FA3"],
                            "blockTimeJourneyLog": "01:00",
                        },
                    ],
                )

        report = LiveCrewHoursService(FakeCrewClient()).get_crew_hours_report(
            "2026-06-01", "2026-06-30", position="Cockpit"
        )
        self.assertEqual(report.records_count, 3)
        self.assertEqual(report.total_flights, 2)
        self.assertEqual(report.official_totals_available, 1)
        self.assertEqual(report.official_totals_unavailable, 1)

    def test_mcp_position_filter_requires_a_report_position_column(self):
        class FakeCrewClient:
            def fetch_official_totals(self, from_date, to_date):
                return OfficialMcpReport(
                    {"AKA": "01:00"},
                    [{"scope_row_unique_id": "leg-position", "crew_codes": ["AKA"], "blockTimeJourneyLog": "01:00"}],
                )

        with self.assertRaises(CrewHoursCapabilityError) as raised:
            LiveCrewHoursService(FakeCrewClient()).get_crew_hours_report(
                "2026-06-01", "2026-06-30", position="Cockpit"
            )
        self.assertIn("position data", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
