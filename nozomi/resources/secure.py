"""
Nozomi
Secure Resource Module
author: hugh@blinkybeach.com
"""
from typing import Any, Union, List
from nozomi.errors.not_authorised import NotAuthorised
from nozomi.data.datastore import Datastore
from nozomi.security.broadcastable import Broadcastable
from nozomi.api.security.session import Session
from nozomi.security.agent import Agent
from nozomi.resources.resource import Resource
from nozomi.http.query_string import QueryString
from nozomi.http.headers import Headers
from nozomi.security.perspective import Perspective
from nozomi.security.forwarded_agent import ForwardedAgent
from nozomi.security.protected import Protected
from nozomi.data.encodable import Encodable
from typing import Optional, Tuple, Set, Type
from nozomi.security.abstract_session import AbstractSession
from nozomi.ancillary.configuration import Configuration


class SecureResource(Resource):
    """
    Abstract class defining an interface for API requests that require
    authentication. Authorisation should be performed in the implementing
    subclass. To authorise a request, call SecureResource.authorise() in the
    subclass compute_response() method.

    Optionally supply an InternalKey to authorise internal requests. The
    underlying retreived resource will need to allow broadcast to the
    Machine Agent.
    """

    def __init__(
        self,
        datastore: Datastore,
        configuration: Configuration,
        session_implementation: Type[AbstractSession],
        requests_may_change_state: bool = False
    ) -> None:

        super().__init__(
            datastore=datastore,
            configuration=configuration,
            requests_may_change_state=requests_may_change_state
        )
        if not isinstance(self.allowed_perspectives, set):
            raise NotImplementedError('Implement .allowed_perspectives')
        if False in [
            isinstance(p, Perspective) for p in self.allowed_perspectives
        ]:
            raise TypeError('.allowed_perspectives must be Set[Perspective]')
        self._session_implementation = session_implementation
        return

    allowed_perspectives: Set[Perspective] = NotImplemented

    def compute_response(
        self,
        query: Optional[QueryString],
        unauthorised_agent: Agent,
        request_data: Optional[Any],
    ) -> Tuple[Union[Broadcastable, List[Broadcastable]], Agent]:
        # Method returning an encodable response, and an Agent authorised to
        # make the request.
        raise NotImplementedError

    def serve(
        self,
        headers: Headers,
        query: Optional[QueryString],
        request_data: Optional[Any],
        session: Session = None
    ) -> str:

        SessionImplementation = self._session_implementation

        if session is None:
            session = SessionImplementation.from_headers(
                headers,
                self.datastore
            )
        if session is not None:
            if (
                    session.perspective not in self.allowed_perspectives
            ):
                raise NotAuthorised

        if session is None and self.configuration.internal_key is None:
            raise NotAuthorised

        if session is None:
            unauthorised_agent = ForwardedAgent.from_headers(
                internal_key=self.configuration.internal_key,
                headers=headers,
                datastore=self.datastore,
                configuration=self.configuration
            )
        else:
            unauthorised_agent = session.agent

        response, authorised_agent = self.compute_response(
            request_data,
            query,
            unauthorised_agent
        )

        if not isinstance(authorised_agent, Agent):
            raise NotAuthorised('')

        if session is not None:
            if authorised_agent != session.agent:
                raise NotAuthorised
            assert authorised_agent == session.agent

        if isinstance(response, list):
            return Broadcastable.serialise_many(
                Broadcastable.broadcast_many_to(response, authorised_agent)
            )

        return response.broadcast_to(authorised_agent).serialise()

    def assert_read_available_to(
        self,
        unauthorised_agent: Agent,
        broadcast_candidate: Protected
    ) -> Agent:
        """
        Raise a NotAuthorised error if this Agent may not read the candidate
        """
        if not broadcast_candidate.grants_read_to(unauthorised_agent):
            raise NotAuthorised
        return unauthorised_agent

    class AcknowledgementBroadcast(Broadcastable):
        """
        Canned Broadcastable response useful in cases where an acknolwedgement
        response is desired but a broadcast of a protect object is not.
        """
        _DATA = {'result': 'ok'}

        def broadcast_to(self, _) -> Encodable:
            return Resource.ResponseData(self._DATA)
