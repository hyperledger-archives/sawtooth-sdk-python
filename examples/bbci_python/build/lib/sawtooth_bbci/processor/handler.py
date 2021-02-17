# Copyright 2016-2018 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ------------------------------------------------------------------------------

import logging

from sawtooth_bbci.processor.bbci_payload import BBCIPayload
from sawtooth_bbci.processor.bbci_state import Game
from sawtooth_bbci.processor.bbci_state import BBCIState
from sawtooth_bbci.processor.bbci_state import BBCI_NAMESPACE

from sawtooth_sdk.processor.handler import TransactionHandler
from sawtooth_sdk.processor.exceptions import InvalidTransaction
from sawtooth_sdk.processor.exceptions import InternalError


LOGGER = logging.getLogger(__name__)


class BBCITransactionHandler(TransactionHandler):
    # Disable invalid-overridden-method. The sawtooth-sdk expects these to be
    # properties.
    # pylint: disable=invalid-overridden-method
    @property
    def family_name(self):
        return 'bbci'

    @property
    def family_versions(self):
        return ['1.0']

    @property
    def namespaces(self):
        return [BBCI_NAMESPACE]

    def apply(self, transaction, context):

        header = transaction.header
        signer = header.signer_public_key

        bbci_payload = BBCIPayload.from_bytes(transaction.payload)

        bbci_state = BBCIState(context)

        if bbci_payload.action == 'delete':
            game = bbci_state.get_game(bbci_payload.name)

            if game is None:
                raise InvalidTransaction(
                    'Invalid action: game does not exist')

            bbci_state.delete_game(bbci_payload.name)

        elif bbci_payload.action == 'create':

            if bbci_state.get_game(bbci_payload.name) is not None:
                raise InvalidTransaction(
                    'Invalid action: Game already exists: {}'.format(
                        bbci_payload.name))

            game = Game(name=bbci_payload.name,
                        board="-" * 9,
                        state="P1-NEXT",
                        player1="",
                        player2="")

            bbci_state.set_game(bbci_payload.name, game)
            _display("Player {} created a game.".format(signer[:6]))

        elif bbci_payload.action == 'take':
            game = bbci_state.get_game(bbci_payload.name)

            if game is None:
                raise InvalidTransaction(
                    'Invalid action: Take requires an existing game')

            if game.state in ('P1-WIN', 'P2-WIN', 'TIE'):
                raise InvalidTransaction('Invalid Action: Game has ended')

            if (game.player1 and game.state == 'P1-NEXT'
                and game.player1 != signer) or \
                    (game.player2 and game.state == 'P2-NEXT'
                     and game.player2 != signer):
                raise InvalidTransaction(
                    "Not this player's turn: {}".format(signer[:6]))

            if game.board[bbci_payload.space - 1] != '-':
                raise InvalidTransaction(
                    'Invalid Action: space {} already taken'.format(
                        bbci_payload))

            if game.player1 == '':
                game.player1 = signer

            elif game.player2 == '':
                game.player2 = signer

            upd_board = _update_board(game.board,
                                      bbci_payload.space,
                                      game.state)

            upd_game_state = _update_game_state(game.state, upd_board)

            game.board = upd_board
            game.state = upd_game_state

            bbci_state.set_game(bbci_payload.name, game)
            _display(
                "Player {} takes space: {}\n\n".format(
                    signer[:6],
                    bbci_payload.space)
                + _game_data_to_str(
                    game.board,
                    game.state,
                    game.player1,
                    game.player2,
                    bbci_payload.name))

        else:
            raise InvalidTransaction('Unhandled action: {}'.format(
                bbci_payload.action))


def _update_board(board, space, state):
    if state == 'P1-NEXT':
        mark = 'X'
    elif state == 'P2-NEXT':
        mark = 'O'

    index = space - 1

    # replace the index-th space with mark, leave everything else the same
    return ''.join([
        current if square != index else mark
        for square, current in enumerate(board)
    ])


def _update_game_state(game_state, board):
    x_wins = _is_win(board, 'X')
    o_wins = _is_win(board, 'O')

    if x_wins and o_wins:
        raise InternalError('Two winners (there can be only one)')

    if x_wins:
        return 'P1-WIN'

    if o_wins:
        return 'P2-WIN'

    if '-' not in board:
        return 'TIE'

    if game_state == 'P1-NEXT':
        return 'P2-NEXT'

    if game_state == 'P2-NEXT':
        return 'P1-NEXT'

    if game_state in ('P1-WINS', 'P2-WINS', 'TIE'):
        return game_state

    raise InternalError('Unhandled state: {}'.format(game_state))


def _is_win(board, letter):
    wins = ((1, 2, 3), (4, 5, 6), (7, 8, 9),
            (1, 4, 7), (2, 5, 8), (3, 6, 9),
            (1, 5, 9), (3, 5, 7))

    for win in wins:
        if (board[win[0] - 1] == letter
                and board[win[1] - 1] == letter
                and board[win[2] - 1] == letter):
            return True
    return False


def _game_data_to_str(board, game_state, player1, player2, name):
    board = list(board.replace("-", " "))
    out = ""
    out += "GAME: {}\n".format(name)
    out += "PLAYER 1: {}\n".format(player1[:6])
    out += "PLAYER 2: {}\n".format(player2[:6])
    out += "STATE: {}\n".format(game_state)
    out += "\n"
    out += "{} | {} | {}\n".format(board[0], board[1], board[2])
    out += "---|---|---\n"
    out += "{} | {} | {}\n".format(board[3], board[4], board[5])
    out += "---|---|---\n"
    out += "{} | {} | {}".format(board[6], board[7], board[8])
    return out


def _display(msg):
    n = msg.count("\n")

    if n > 0:
        msg = msg.split("\n")
        length = max(len(line) for line in msg)
    else:
        length = len(msg)
        msg = [msg]

    # pylint: disable=logging-not-lazy
    LOGGER.debug("+" + (length + 2) * "-" + "+")
    for line in msg:
        LOGGER.debug("+ " + line.center(length) + " +")
    LOGGER.debug("+" + (length + 2) * "-" + "+")
