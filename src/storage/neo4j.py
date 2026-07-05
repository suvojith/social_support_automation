"""Neo4j client: family/employment graph.

Family members are modeled as individual Person nodes rather than a headcount,
so the validation agent can query for members whose details disagree between
source documents.
"""

from __future__ import annotations

from neo4j import GraphDatabase

from src.config.settings import get_settings


class Neo4jStore:
    def __init__(self, uri: str | None = None, user: str | None = None, password: str | None = None):
        s = get_settings()
        self.driver = GraphDatabase.driver(uri or s.neo4j_uri, auth=(user or s.neo4j_user, password or s.neo4j_password))

    def close(self):
        self.driver.close()

    def init_constraints(self):
        with self.driver.session() as session:
            session.run("CREATE CONSTRAINT applicant_id IF NOT EXISTS FOR (a:Applicant) REQUIRE a.id IS UNIQUE")
            session.run("CREATE CONSTRAINT person_id IF NOT EXISTS FOR (p:Person) REQUIRE p.id IS UNIQUE")

    def upsert_applicant(self, application_id: str, name: str, emirates_id: str):
        with self.driver.session() as session:
            session.run(
                "MERGE (a:Applicant {id: $aid}) SET a.name = $name, a.emirates_id = $eid",
                aid=application_id,
                name=name,
                eid=emirates_id,
            )

    def upsert_family_member(
        self,
        application_id: str,
        member_id: str,
        name: str,
        dob: str,
        relation: str,
        source_doc: str,
    ):
        """Create a Person node and a DECLARES relationship from the applicant.

        Multiple mentions of the same name from different docs create separate nodes
        so the conflict-check query (find_conflicting_dobs) can detect DOB disagreements.
        """
        with self.driver.session() as session:
            session.run(
                """
                MATCH (a:Applicant {id: $aid})
                MERGE (p:Person {id: $mid})
                SET p.name = $name, p.dob = $dob, p.source_doc = $src
                MERGE (a)-[:DECLARES {relation: $rel, source_doc: $src}]->(p)
                """,
                aid=application_id,
                mid=member_id,
                name=name,
                dob=dob,
                rel=relation,
                src=source_doc,
            )

    def upsert_employment(self, application_id: str, employer: str, role: str, years: float):
        with self.driver.session() as session:
            session.run(
                """
                MATCH (a:Applicant {id: $aid})
                MERGE (e:Employer {name: $emp})
                MERGE (a)-[:WORKED_AT {role: $role, years: $yrs}]->(e)
                """,
                aid=application_id,
                emp=employer,
                role=role,
                yrs=years,
            )

    def find_conflicting_dobs(self, application_id: str) -> list[dict]:
        """Flag family members whose DOB disagrees across source documents."""
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (app:Applicant {id: $aid})-[:DECLARES]->(m:Person)
                WITH m.name AS name, collect(DISTINCT m.dob) AS dobs,
                     collect(DISTINCT m.source_doc) AS sources
                WHERE size(dobs) > 1
                RETURN name, dobs, sources
                """,
                aid=application_id,
            )
            return [dict(r) for r in result]

    def find_conflicting_addresses(self, application_id: str) -> list[dict]:
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (a:Applicant {id: $aid})
                RETURN a.address_form AS form_addr, a.address_credit AS credit_addr,
                       a.address_form <> a.address_credit AS mismatch
                """,
                aid=application_id,
            )
            return [dict(r) for r in result]

    def clear_all(self):
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
